"""Pegasus frontend adapter."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path, PurePosixPath

from retrolibx.core.models import (
    Capabilities,
    Diagnostic,
    Game,
    LaunchConfig,
    Library,
    Media,
    Rom,
    System,
)
from retrolibx.core.normalize import parse_bool, parse_date, parse_players
from retrolibx.core.operations import ExportIntent, FileRequest, TextRequest
from retrolibx.core.options import ExportOptions, ImportOptions
from retrolibx.core.source_profiles import SourceProfile
from retrolibx.errors import ParseError
from retrolibx.utils import FileIndex, find_metadata
from retrolibx.utils.discovery import rom_relative_path
from retrolibx.utils.encoding import detect_metadata_encoding

from ..base import DetectionResult, ImportResult, LibraryAdapter
from .metadata import field, parse_metadata, render_records
from .media import canonical_role
from retrolibx.core.media import supported_media


class PegasusAdapter(LibraryAdapter):
    name = "pegasus"
    aliases = ()
    capabilities = Capabilities(
        artwork=True, video=True, collections=True, favorites=True, launch_config=True
    )

    @staticmethod
    def _metadata_files(path: Path) -> list[Path]:
        return find_metadata(path, ("metadata.pegasus.txt",))

    @classmethod
    def detect(cls, path: Path) -> DetectionResult:
        files = cls._metadata_files(path)
        return DetectionResult(
            format=cls.name,
            confidence=0.96 if files else 0.0,
            evidence=[f"{len(files)} Pegasus metadata file(s)"] if files else [],
        )

    def import_library(self, path: Path, options: ImportOptions) -> ImportResult:
        profile = SourceProfile.load(options.source_profile)
        root = path if path.is_dir() else path.parent
        metadata_files = self._metadata_files(path)
        if options.platforms:
            requested = set(options.platforms)
            available = {p.parent.relative_to(root).as_posix(): p for p in metadata_files}
            missing = requested - available.keys()
            if missing:
                raise ParseError(f"Unknown source platform(s): {', '.join(sorted(missing))}")
            metadata_files = [available[key] for key in sorted(requested)]
        systems: list[System] = []
        diagnostics: list[Diagnostic] = []
        for metadata_path in metadata_files:
            # Limit fallbacks to this platform; nested metadata marks a separate library.
            scope_root = metadata_path.parent if options.platforms else root
            resolver = FileIndex(
                scope_root, exclude=metadata_files, platform_boundary=bool(options.platforms)
            )
            try:
                metadata_bytes = metadata_path.read_bytes()
                encoding = detect_metadata_encoding(metadata_bytes) if options.metadata_encoding == "auto" else options.metadata_encoding
                text = metadata_bytes.decode(encoding)
            except (OSError, UnicodeError, LookupError) as exc:
                raise ParseError(f"Could not read {metadata_path}: {exc}") from exc
            records = parse_metadata(text)
            if not records or not any("collection" in record for record in records):
                raise ParseError(f"No collection in {metadata_path}")
            if sum("collection" in record for record in records) != 1:
                raise ParseError(
                    f"Multiple collections in one metadata file are not supported: {metadata_path}"
                )
            collection: dict[str, list[str]] = {}
            game_records: list[dict[str, list[str]]] = []
            for record in records:
                if "collection" in record and "game" not in record:
                    collection.update(record)
                elif "game" in record:
                    game_records.append(record)
            collection_name = field(collection, "collection") or metadata_path.parent.name
            shortname = field(collection, "shortname") or collection_name
            system_record = (
                self.systems.resolve(metadata_path.parent.name)
                or self.systems.resolve(shortname)
                or self.systems.resolve(collection_name)
            )
            system = System(
                id=system_record.id
                if system_record
                else re.sub(r"[^\w-]", "-", shortname.casefold()).strip("-") or "custom",
                name=system_record.name if system_record else collection_name,
                metadata={
                    "pegasus": collection,
                    "source_root": str(metadata_path.parent.resolve()),
                    "source_platform": metadata_path.parent.relative_to(root).as_posix(),
                    "metadata_sha256": hashlib.sha256(metadata_bytes).hexdigest(),
                },
            )
            for record_index, record in enumerate(game_records):
                filenames = [
                    value for key in ("file", "files") for value in record.get(key, []) if value
                ]
                if not filenames:
                    diagnostics.append(
                        Diagnostic(
                            severity="error",
                            code="missing-rom-reference",
                            message="Pegasus game has no file",
                            path=metadata_path,
                            game_name=field(record, "game"),
                        )
                    )
                    continue
                roms = []
                for filename in filenames:
                    reference = PurePosixPath(filename.replace("\\", "/"))
                    if ".." in reference.parts or "\n" in filename or "\r" in filename:
                        raise ParseError(f"Unsafe ROM reference: {filename!r}")
                    resolved = resolver.resolve(
                        filename,
                        bases=(metadata_path.parent,),
                        preferred_parts=("rom", "roms", system.id),
                        strict_relative=True,
                    )
                    actual = resolved or (metadata_path.parent / filename).resolve(strict=False)
                    if (
                        options.platforms
                        and resolved
                        and not actual.is_relative_to(scope_root.resolve())
                    ):
                        raise ParseError(f"ROM outside source platform: {filename}")
                    if options.platforms and any(
                        (parent / "metadata.pegasus.txt").is_file()
                        for parent in actual.parents
                        if parent != scope_root.resolve()
                        and parent.is_relative_to(scope_root.resolve())
                    ):
                        raise ParseError(f"ROM belongs to nested source platform: {filename}")
                    relative = (
                        actual.relative_to(metadata_path.parent.resolve()).as_posix()
                        if actual.is_relative_to(metadata_path.parent.resolve())
                        else reference.name
                    )
                    roms.append(
                        Rom(
                            path=actual,
                            metadata={"source_path": filename, "relative_path": relative},
                        )
                    )
                players_min, players_max = parse_players(field(record, "players"))
                raw_rating = field(record, "rating")
                try:
                    rating = float(raw_rating) if raw_rating else None
                    if rating is not None and rating > 1:
                        rating /= 100.0
                    if rating is not None:
                        rating = max(0.0, min(1.0, rating))
                except ValueError:
                    rating = None
                assets: dict[str, Path] = {}
                for key, values in record.items():
                    if not key.startswith("assets.") or not values:
                        continue
                    kind = canonical_role(key.removeprefix("assets."))
                    value = values[-1]
                    if ".." in PurePosixPath(value.replace("\\", "/")).parts:
                        raise ParseError(f"Unsafe media reference: {value}")
                    aliased = options.media_path_aliases.get(system.metadata["source_platform"], {}).get(value)
                    resolved_asset = aliased.resolve() if aliased else resolver.resolve(
                        value, bases=(metadata_path.parent,), preferred_parts=("media", "images", kind),
                    )
                    if (
                        options.platforms
                        and resolved_asset
                        and not resolved_asset.is_relative_to(scope_root.resolve())
                        and not (options.shared_media_root and resolved_asset.is_relative_to(options.shared_media_root.resolve()))
                    ):
                        raise ParseError(f"Media outside source platform: {value}")
                    assets[kind] = resolved_asset or (metadata_path.parent / value).resolve(
                        strict=False
                    )
                game_name = field(record, "game") or Path(filenames[0]).stem
                for role, basename in profile.media_fallbacks.items():
                    aliases = (role, "boxfront") if role == "box_front" else (role,)
                    existing = next((assets[k] for k in aliases if k in assets), None)
                    if existing and existing.is_file() and supported_media(existing, role):
                        assets[aliases[0]] = existing
                        continue
                    if profile.media_directory is None:
                        continue
                    folder = metadata_path.parent / profile.media_directory / game_name
                    stems = basename if isinstance(basename, list) else [basename]
                    names = {name.casefold() for name in stems}
                    candidates = (
                        [
                            p
                            for p in folder.iterdir()
                            if p.is_file()
                            and p.stem.casefold() in names
                            and supported_media(p, role)
                            and p.resolve().is_relative_to(scope_root.resolve())
                        ]
                        if folder.is_dir()
                        and folder.resolve().is_relative_to(metadata_path.parent.resolve())
                        else []
                    )
                    if len(candidates) == 1:
                        assets[aliases[0]] = candidates[0].resolve()
                        if existing:
                            diagnostics.append(
                                Diagnostic(
                                    severity="info",
                                    code="repaired-media-reference",
                                    message=f"{game_name}: {existing} -> {candidates[0]}",
                                    path=metadata_path,
                                    game_name=game_name,
                                )
                            )
                    else:
                        diagnostics.append(
                            Diagnostic(
                                severity="warning",
                                code="missing-media",
                                message=f"{game_name}: {aliases[0]} media missing or ambiguous",
                                path=metadata_path,
                                game_name=game_name,
                            )
                        )
                if "boxfront" in assets:
                    assets.setdefault("box_front", assets.pop("boxfront"))
                media_fields = {
                    role: assets.pop(role)
                    for role in Media.model_fields
                    if role != "extra" and role in assets
                }
                media = Media(**media_fields, extra=assets)
                known = {
                    "game",
                    "file",
                    "sort",
                    "description",
                    "developer",
                    "publisher",
                    "genre",
                    "release",
                    "players",
                    "rating",
                    "favorite",
                    "launch",
                }
                unknown = {
                    key: value
                    for key, value in record.items()
                    if key not in known and not key.startswith("assets.")
                }
                game = Game(
                    name=game_name,
                    sort_name=field(record, "sort") or field(record, "sort-by"),
                    roms=roms,
                    media=media,
                    description=(
                        field(record, "description") or field(record, "summary") or ""
                    ).replace("\\n", "\n") or None,
                    developer=field(record, "developer"),
                    publisher=field(record, "publisher"),
                    genre=[
                        part.strip()
                        for part in re.split(r"[,;]", field(record, "genre") or "")
                        if part.strip()
                    ],
                    release_date=parse_date(field(record, "release")),
                    players_min=players_min,
                    players_max=players_max,
                    rating=rating,
                    favorite=parse_bool(field(record, "favorite")),
                    launch=LaunchConfig(
                        command=field(record, "launch") or field(collection, "launch")
                    ) if field(record, "launch") or field(collection, "launch") else None,
                    source_metadata={
                        "pegasus": unknown, "pegasus_fields": record,
                        "pegasus_record_index": record_index,
                    },
                )
                profile.normalize_game(game)
                system.games.append(game)
            systems.append(system)
        library = Library(
            format=self.name, source_path=root, systems=systems, diagnostics=diagnostics,
            metadata={"source_profile": profile.model_dump(mode="json")},
        )
        return ImportResult(library=library, diagnostics=diagnostics)

    def render_library(
        self, library: Library, target: Path, options: ExportOptions
    ) -> ExportIntent:
        del target
        intent = ExportIntent()
        for system in sorted(library.systems, key=lambda item: item.id):
            record = self.systems.records.get(system.id)
            mapping = record.platforms.get("pegasus") if record else None
            directory = (
                record.rom_directory
                if record and record.rom_directory
                else mapping.shortname[0]
                if mapping and mapping.shortname
                else system.id
            )
            directory = system.metadata.get("export_directory", directory)
            collection_fields: list[tuple[str, str | None]] = [
                ("collection", system.name),
                ("shortname", system.id),
            ]
            extensions = sorted(
                {
                    rom.path.suffix.lstrip(".")
                    for game in system.games
                    for rom in game.roms
                    if rom.path.suffix
                }
            )
            collection_fields.append(("extension", " ".join(extensions)))
            original_collection = system.metadata.get("pegasus", {})
            for key, values in original_collection.items():
                if key not in {"collection", "shortname", "extension", "extensions"}:
                    collection_fields.extend((key, value) for value in values)
            records: list[list[tuple[str, str | None]]] = [collection_fields]
            for game in sorted(system.games, key=lambda item: item.sort_name or item.name):
                game_fields: list[tuple[str, str | None]] = [("game", game.name)]
                for rom in game.roms:
                    relative = rom_relative_path(rom.path, rom.metadata).as_posix()
                    destination = PurePosixPath(directory) / relative
                    intent.files.append(
                        FileRequest(source=rom.path, destination=destination, category="rom")
                    )
                    game_fields.append(("file", relative))
                game_fields.extend(
                    [
                        ("sort", game.sort_name),
                        ("description", game.description),
                        ("developer", game.developer),
                        ("publisher", game.publisher),
                        ("genre", ", ".join(game.genre) or None),
                        ("release", game.release_date.isoformat() if game.release_date else None),
                        ("players", self._players(game)),
                        (
                            "rating",
                            str(round(game.rating * 100)) if game.rating is not None else None,
                        ),
                        (
                            "favorite",
                            "true"
                            if game.favorite
                            else "false"
                            if game.favorite is not None
                            else None,
                        ),
                        ("launch", game.launch.command if game.launch else None),
                    ]
                )
                original_fields = game.source_metadata.get("pegasus_fields", {})
                written = {key for key, value in game_fields if value is not None and value != ""}
                for key, values in original_fields.items():
                    if key not in written | {"files"} and not key.startswith("assets."):
                        game_fields.extend((key, value) for value in values)
                for kind, media in game.media.items():
                    media_relative = PurePosixPath(
                        rom_relative_path(game.roms[0].path, game.roms[0].metadata).as_posix()
                    )
                    destination = (
                        PurePosixPath(directory)
                        / "media"
                        / media_relative.with_name(
                            f"{media_relative.stem}-{kind}{media.suffix or '.png'}"
                        )
                    )
                    intent.files.append(
                        FileRequest(source=media, destination=destination, category="media")
                    )
                    game_fields.append(
                        (f"assets.{kind}", destination.relative_to(directory).as_posix())
                    )
                records.append(game_fields)
            intent.texts.append(
                TextRequest(
                    destination=PurePosixPath(directory) / "metadata.pegasus.txt",
                    content=render_records(records),
                )
            )
        return intent

    @staticmethod
    def _players(game: Game) -> str | None:
        if game.players_min is None:
            return None
        if game.players_max is None or game.players_max == game.players_min:
            return str(game.players_min)
        return f"{game.players_min}-{game.players_max}"
