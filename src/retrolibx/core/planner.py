"""Resolve export intent into a safe, auditable conversion plan."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

from retrolibx import __version__
from retrolibx.errors import ConflictError, ValidationError

from .operations import (
    ConversionPlan,
    CreateDirectory,
    ExportIntent,
    TransferFile,
    WriteManifest,
    WriteText,
    WriteSourceMetadata,
    MigrateSourceMedia,
)
from .options import ConflictPolicy, ExportOptions, MediaMode, RomMode


def _resolved(path: Path) -> Path:
    return path.expanduser().resolve(strict=False)


def _destination(root: Path, relative: PurePosixPath) -> Path:
    if relative.is_absolute() or ".." in relative.parts:
        raise ValidationError(f"Target path escapes output root: {relative}")
    destination = root.joinpath(*relative.parts)
    try:
        destination.resolve(strict=False).relative_to(root.resolve(strict=False))
    except ValueError as exc:
        raise ValidationError(f"Target path escapes output root: {relative}") from exc
    return destination


def _renamed(path: Path, occupied: set[Path]) -> Path:
    index = 2
    candidate = path
    while candidate.exists() or candidate in occupied:
        candidate = path.with_name(f"{path.stem} ({index}){path.suffix}")
        index += 1
    return candidate


class ConversionPlanner:
    def plan(
        self,
        intent: ExportIntent,
        *,
        source_root: Path,
        target_root: Path,
        source_format: str,
        target_format: str,
        options: ExportOptions,
    ) -> ConversionPlan:
        source = _resolved(source_root)
        target = _resolved(target_root)
        if source == target and not options.in_place:
            raise ValidationError("Source and target resolve to the same location; use --in-place")

        operations: list[CreateDirectory | TransferFile | WriteText | WriteManifest | WriteSourceMetadata | MigrateSourceMedia] = []
        occupied: set[Path] = set()
        for relative in sorted(set(intent.directories), key=str):
            operations.append(CreateDirectory(destination=_destination(target, relative)))

        for request in sorted(intent.files, key=lambda item: str(item.destination)):
            destination = _destination(target, request.destination)
            if destination in occupied:
                raise ConflictError(f"Multiple operations target the same path: {destination}")
            destination, overwrite, skipped, reason = self._conflict(
                destination, request.source, occupied, options.conflict
            )
            occupied.add(destination)
            mode: RomMode | MediaMode = (
                options.rom_mode if request.category == "rom" else options.media_mode
            )
            # The legacy symbolic-link alias is outside this project's test scope.
            if mode == RomMode.LINK:  # pragma: no cover
                mode = RomMode.SYMLINK
            if request.category == "rom" and mode == RomMode.NONE:
                skipped, reason = True, "ROM mode is none"
            operations.append(
                TransferFile(
                    source=request.source,
                    destination=destination,
                    category=request.category,
                    mode=mode,
                    overwrite=overwrite,
                    skipped=skipped,
                    skip_reason=reason,
                )
            )

        for text_request in sorted(intent.texts, key=lambda item: str(item.destination)):
            destination = _destination(target, text_request.destination)
            if destination in occupied:
                raise ConflictError(f"Multiple operations target the same path: {destination}")
            if text_request.expected_sha256 is not None:
                overwrite, skipped, reason = True, False, None
            else:
                destination, overwrite, skipped, reason = self._conflict(
                    destination, None, occupied, options.conflict
                )
            occupied.add(destination)
            operations.append(
                WriteText(
                    destination=destination,
                    content=text_request.content,
                    overwrite=overwrite,
                    skipped=skipped,
                    skip_reason=reason,
                    expected_sha256=text_request.expected_sha256,
                    backup=text_request.backup,
                )
            )

        written = [
            str(operation.destination.relative_to(target))
            for operation in operations
            if not isinstance(operation, CreateDirectory)
            and not getattr(operation, "skipped", False)
        ]
        manifest = {
            "version": 1,
            "generated_by": "retrolibx",
            "tool_version": __version__,
            "generated_at": datetime.now(UTC).isoformat(),
            "format": target_format,
            "source": {"format": source_format, "path": str(source)},
            "policies": {
                "rom_mode": options.rom_mode.value,
                "media_mode": options.media_mode.value,
                "conflict": options.conflict.value,
            },
            "files": sorted(written),
            "shared_media": options.shared_pegasus,
        }
        if intent.source_metadata_updates or intent.media_relocations:
            if not options.shared_pegasus or source_format != "pegasus" or target_format != "es-de":
                raise ValidationError("Source mutations require explicit Pegasus-to-ES-DE shared media mode")
            if options.rom_mode != RomMode.NONE or options.media_mode != MediaMode.COPY:
                raise ValidationError("Shared media requires ROM mode none and media mode copy")
            if source.is_relative_to(target) or target.is_relative_to(source):
                raise ValidationError("Shared media source and target directories overlap")
            updates: set[Path] = set()
            for request in intent.source_metadata_updates:
                path = _resolved(request.source)
                if not path.is_relative_to(source) or path.name != "metadata.pegasus.txt" or path in updates:
                    raise ValidationError("Invalid source metadata update")
                updates.add(path)
                operations.append(WriteSourceMetadata(
                    destination=path, content_base64=request.content_base64,
                    expected_sha256=request.expected_sha256,
                ))
            transfers = {(op.source.resolve(), op.destination) for op in operations if isinstance(op, TransferFile) and op.category == "media"}
            migrated: set[Path] = set()
            for request in intent.media_relocations:
                path = _resolved(request.source)
                targets = [_destination(target, relative) for relative in request.destinations]
                if (
                    not path.is_relative_to(source) or path in updates or path in migrated or not targets
                    or any((path, destination) not in transfers for destination in targets)
                ):
                    raise ValidationError("Invalid source media relocation")
                migrated.add(path)
                operations.append(MigrateSourceMedia(
                    destination=path, targets=targets, expected_sha256=request.expected_sha256,
                    cleanup=request.cleanup,
                ))
            manifest["source_metadata_updates"] = sorted(str(path.relative_to(source)) for path in updates)
            manifest["source_media_cleanup"] = [
                str(request.source.relative_to(source)) for request in intent.media_relocations if request.cleanup
            ]
        operations.append(
            WriteManifest(
                destination=_destination(target, PurePosixPath(".retrolibx/manifest.json")),
                content=json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            )
        )
        return ConversionPlan(
            source_root=source,
            target_root=target,
            source_format=source_format,
            target_format=target_format,
            conflict_policy=options.conflict,
            operations=operations,
            diagnostics=list(intent.diagnostics),
        )

    @staticmethod
    def _conflict(
        destination: Path,
        source: Path | None,
        occupied: set[Path],
        policy: ConflictPolicy,
    ) -> tuple[Path, bool, bool, str | None]:
        exists = destination.exists() or destination in occupied
        if not exists:
            return destination, False, False, None
        if policy == ConflictPolicy.ERROR:
            raise ConflictError(f"Target already exists: {destination}")
        if policy == ConflictPolicy.RENAME:
            return _renamed(destination, occupied), False, False, None
        if policy == ConflictPolicy.OVERWRITE:
            return destination, True, False, None
        if policy == ConflictPolicy.NEWER and source is not None and destination.exists():
            if source.stat().st_mtime > destination.stat().st_mtime:
                return destination, True, False, None
            return destination, False, True, "source is not newer"
        return destination, False, True, "target exists"
