"""Plan opt-in media relocation and byte-preserving source metadata patches."""

import base64
import hashlib
from collections import defaultdict
from pathlib import Path, PurePosixPath, PureWindowsPath

from retrolibx.adapters.pegasus.media import canonical_role
from retrolibx.adapters.pegasus.metadata import parse_metadata, patch_asset_references
from retrolibx.core.media import file_digest
from retrolibx.core.models import Diagnostic, Library
from retrolibx.core.operations import ExportIntent, MediaRelocation, SourceMetadataUpdate
from retrolibx.errors import ParseError, ValidationError
from retrolibx.utils import FileIndex, find_metadata
from retrolibx.utils.encoding import detect_metadata_encoding


def prepare_shared_media(
    library: Library, intent: ExportIntent, source_root: Path, media_base: str,
    encoding: str, *, device_index: bool = False, retained_sources: set[Path] | None = None,
) -> None:
    """Add explicit source mutations; do not copy, patch or delete any file here."""
    if library.format != "pegasus":
        raise ValidationError("Shared media migration requires a Pegasus source")
    root = source_root.resolve()
    base = media_base.replace("\\", "/")
    if (
        not (PurePosixPath(base).is_absolute() or PureWindowsPath(base).is_absolute())
        or ".." in PurePosixPath(base).parts or any(c in base for c in "\r\n\t\x00")
    ):
        raise ValidationError("Shared media directory must be absolute")
    systems = {system.id: system for system in library.systems}
    if len(systems) != len(library.systems):
        raise ValidationError("Shared media migration requires unique source systems")
    by_destination = {request.destination: request.source.resolve() for request in intent.files if request.category == "media"}
    edits: dict[Path, dict[int, dict[str, str]]] = defaultdict(lambda: defaultdict(dict))
    baselines: dict[Path, str] = {}
    for binding in intent.media_bindings:
        if binding.role not in {"box_front", "logo", "video"}:
            raise ValidationError("Shared media only supports cover, logo and video")
        if not binding.destination.parts or binding.destination.parts[0] != "downloaded_media":
            raise ValidationError("Invalid shared media destination")
        system = systems[binding.system_id]
        metadata = (Path(system.metadata["source_root"]) / "metadata.pegasus.txt").resolve()
        if not metadata.is_relative_to(root) or metadata.is_symlink():
            raise ValidationError("Source metadata escaped the selected library")
        game = system.games[binding.game_index]
        record_index = game.source_metadata["pegasus_record_index"]
        relative = PurePosixPath(*binding.destination.parts[1:]).as_posix()
        edits[metadata][record_index][binding.role] = base.rstrip("/") + "/" + relative
        baselines[metadata] = system.metadata["metadata_sha256"]
    for metadata, replacements in edits.items():
        raw = metadata.read_bytes()
        if hashlib.sha256(raw).hexdigest() != baselines[metadata]:
            raise ValidationError(f"Source metadata changed during planning: {metadata}")
        actual_encoding = detect_metadata_encoding(raw) if encoding == "auto" else encoding
        patched = patch_asset_references(raw, replacements, actual_encoding)
        if patched != raw:
            intent.source_metadata_updates.append(SourceMetadataUpdate(
                source=metadata, expected_sha256=baselines[metadata],
                content_base64=base64.b64encode(patched).decode("ascii"),
            ))

    grouped: dict[Path, list[PurePosixPath]] = defaultdict(list)
    for destination, source in by_destination.items():
        if not source.is_relative_to(root) or source.is_symlink():
            # Existing ES-DE assets remain read-only sources; all variant copies
            # still participate in verification before changing source metadata.
            if device_index or source.is_symlink() or not source.is_relative_to(Path(base).resolve()):
                raise ValidationError(f"Media source escaped the selected library: {source}")
            if not intent.source_metadata_updates:
                # A repeat export with no source edits/cleanup needs no migration.
                continue
        grouped[source].append(destination)
    roms = {rom.path.resolve() for system in library.systems for game in system.games for rom in game.roms}
    metadata_files = find_metadata(root, ("metadata.pegasus.txt",))
    if grouped.keys() & (roms | {path.resolve() for path in metadata_files}):
        raise ValidationError("A media source is also a ROM or metadata file")

    # Retain files still needed by collection defaults, extras or unselected metadata.
    protected = {
        path for path in grouped
        if path.stem.casefold() in {"mini_boxfront", "mini_box_front", "mini_logo"}
    }
    protected.update(path.resolve() for path in retained_sources or set())
    protected.update(path for path in grouped if not path.is_relative_to(root))
    if grouped:
        index = FileIndex(root, exclude=metadata_files)
        for metadata in metadata_files:
            try:
                raw_metadata = metadata.read_bytes()
                actual_encoding = detect_metadata_encoding(raw_metadata) if encoding == "auto" else encoding
                records = parse_metadata(raw_metadata.decode(actual_encoding))
            except (OSError, UnicodeError, LookupError, ValueError, ParseError):
                protected.update(grouped)
                intent.diagnostics.append(Diagnostic(
                    severity="warning", code="shared-source-retained",
                    message="Unreadable metadata prevents safe source-media cleanup", path=metadata,
                ))
                continue
            game_index = -1
            for record in records:
                if "game" in record:
                    game_index += 1
                for key, values in record.items():
                    if not key.startswith("assets."):
                        continue
                    role = canonical_role(key.removeprefix("assets."))
                    if "game" in record and role in edits.get(metadata.resolve(), {}).get(game_index, {}):
                        continue
                    for value in values:
                        resolved = index.resolve(value, bases=(metadata.parent,), preferred_parts=("media", "images", role))
                        if resolved:
                            protected.add(resolved.resolve())
                        elif value:
                            tail = PurePosixPath(value.replace("\\", "/")).name.casefold()
                            protected.update(path for path in grouped if path.name.casefold() == tail)
    for source, destinations in grouped.items():
        if source in protected:
            intent.diagnostics.append(Diagnostic(
                severity="warning", code="shared-source-retained",
                message="Source media retained: mini asset or referenced by other metadata fields", path=source,
            ))
        intent.media_relocations.append(MediaRelocation(
            source=source, destinations=sorted(set(destinations), key=str),
            expected_sha256=None if device_index else file_digest(source),
            cleanup=source not in protected,
        ))
