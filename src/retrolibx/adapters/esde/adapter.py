"""ES-DE metadata and media layout, independent from generic ES exports."""

from pathlib import Path, PurePosixPath

from frontend_platforms import platform_component
from retrolibx.core.models import Capabilities, Diagnostic, Game, Library
from retrolibx.core.operations import ExportIntent, FileRequest, MediaBinding, TextRequest
from retrolibx.core.options import ExportOptions, RomMode
from retrolibx.errors import ValidationError
from retrolibx.utils.discovery import rom_relative_path

from retrolibx.core.media import supported_media
from ..base import DetectionResult
from ..emulationstation.adapter import EmulationStationAdapter
from ..emulationstation.gamelist import write_gamelist


class ESDEAdapter(EmulationStationAdapter):
    name = "es-de"
    aliases = ("esde",)
    platform_id = "es-de"
    capabilities = Capabilities(
        artwork=True, video=True, collections=True, favorites=True, play_stats=True
    )

    @classmethod
    def detect(cls, path: Path) -> DetectionResult:
        files = cls._gamelists(path)
        marker = path / "ES-DE" if path.is_dir() else path.parent / "ES-DE"
        confidence = 0.92 if files and marker.exists() else 0.0
        return DetectionResult(
            format=cls.name,
            confidence=confidence,
            evidence=["ES-DE marker", f"{len(files)} gamelist(s)"] if confidence else [],
        )

    def render_library(
        self, library: Library, target: Path, options: ExportOptions
    ) -> ExportIntent:
        del target
        intent = ExportIntent()
        occupied: set[str] = set()
        for system in library.systems:
            try:
                target_name = platform_component(system.metadata.get("target_system", system.id))
            except ValueError as exc:
                raise ValidationError(str(exc)) from exc
            directory = self.system_directory(system.id) or system.id
            entries: list[tuple[Game, str, dict[str, str]]] = []
            paths: set[str] = set()
            folder_covers: dict[PurePosixPath, tuple[tuple[int, str, str], Path]] = {}
            for game_index, game in enumerate(system.games):
                for rom_index, rom in enumerate(game.roms):
                    relative = PurePosixPath(rom_relative_path(rom.path, rom.metadata).as_posix())
                    rom_path = f"./{relative}"
                    if rom_path in paths:
                        raise ValidationError(f"Duplicate ROM path in {system.id}: {rom_path}")
                    paths.add(rom_path)
                    if options.rom_mode != RomMode.NONE:
                        intent.files.append(
                            FileRequest(
                                source=rom.path,
                                destination=PurePosixPath("ROMs") / directory / relative,
                                category="rom",
                            )
                        )
                    display = game.model_copy(deep=True)
                    if game.source_metadata.get("valid_rom_count", len(game.roms)) > 1:
                        display.name = relative.stem
                    for role, media, folder in (
                        ("box_front", game.media.box_front, "covers"),
                        ("logo", game.media.logo or game.media.marquee, "marquees"),
                        ("video", game.media.video, "videos"),
                    ):
                        if media is None:
                            continue
                        if not media.is_file() or not supported_media(media, role):
                            if rom_index == 0:
                                intent.diagnostics.append(Diagnostic(
                                    severity="warning", code="unsupported-or-missing-media",
                                    message=f"{game.name}: {role} media missing or unsupported",
                                    path=media, system_id=system.id, game_name=game.name,
                                ))
                            continue
                        suffix = media.suffix.lower()
                        if suffix == ".jpeg":
                            suffix = ".jpg"
                        if role == "box_front" and rom.path.is_file():
                            # Use existing ROMs only. Prefer a directly contained game,
                            # then a stable ROM-path order, including ancestor folders.
                            for parent in relative.parents:
                                if parent == PurePosixPath("."):
                                    break
                                priority = (
                                    len(relative.parts) - len(parent.parts),
                                    relative.as_posix().casefold(),
                                    relative.as_posix(),
                                )
                                previous = folder_covers.get(parent)
                                if previous is None or priority < previous[0]:
                                    folder_covers[parent] = (priority, media)
                        destination = (
                            PurePosixPath("downloaded_media")
                            / target_name
                            / folder
                            / relative.with_suffix(suffix)
                        )
                        key = destination.as_posix().casefold()
                        if key in occupied:
                            raise ValidationError(f"Media target collision: {destination}")
                        occupied.add(key)
                        if rom_index == 0:
                            intent.media_bindings.append(MediaBinding(
                                system_id=system.id, game_index=game_index,
                                role=role, destination=destination,
                            ))
                        intent.files.append(
                            FileRequest(
                                source=media,
                                destination=destination,
                                category="media",
                            )
                        )
                    entries.append((display, rom_path, {}))
            for parent, (_, cover) in sorted(folder_covers.items(), key=lambda item: str(item[0])):
                suffix = ".jpg" if cover.suffix.lower() == ".jpeg" else cover.suffix.lower()
                # ES-DE matches folders by their whole directory name, including dots.
                destination = (
                    PurePosixPath("downloaded_media") / target_name / "covers"
                    / parent.with_name(parent.name + suffix)
                )
                key = destination.as_posix().casefold()
                if key in occupied:
                    intent.diagnostics.append(Diagnostic(
                        severity="warning", code="folder-cover-collision",
                        message=f"Folder cover target already used; retaining existing media: {parent}",
                        system_id=system.id,
                    ))
                    continue
                occupied.add(key)
                # No MediaBinding: these copies decorate folders, not source game records.
                intent.files.append(FileRequest(
                    source=cover, destination=destination, category="media",
                ))
            intent.texts.append(
                TextRequest(
                    destination=PurePosixPath("gamelists") / target_name / "gamelist.xml",
                    content=write_gamelist(entries),
                )
            )
        return intent
