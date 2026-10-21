"""Use-case orchestration shared by CLI and future integrations."""

from __future__ import annotations

import hashlib
import zlib
from pathlib import Path

from pydantic import BaseModel

from retrolibx.adapters import AdapterRegistry, builtin_registry
from retrolibx.adapters.base import DetectionResult, LibraryAdapter
from retrolibx.adapters.esde.merge import merge_gamelists
from retrolibx.core.executor import PlanExecutor
from retrolibx.core.models import Diagnostic, Library
from retrolibx.core.operations import ConversionPlan, ExecutionReport
from retrolibx.core.options import ConflictPolicy, ExportOptions, ImportOptions, MediaMode, RomMode
from retrolibx.core.planner import ConversionPlanner
from retrolibx.core.validation import validate_library
from retrolibx.core.entries import select_entries
from retrolibx.errors import ValidationError
from retrolibx.registry import SystemRegistry
from retrolibx.utils.discovery import rom_relative_path

from .shared_media import prepare_shared_media


class ConversionResult(BaseModel):
    library: Library
    plan: ConversionPlan
    execution: ExecutionReport | None = None


class ConversionService:
    def __init__(
        self,
        adapters: AdapterRegistry | None = None,
        planner: ConversionPlanner | None = None,
        executor: PlanExecutor | None = None,
        platform_config_dir: Path | None = None,
    ) -> None:
        self.adapters = adapters or builtin_registry(
            SystemRegistry.load(platform_config_dir=platform_config_dir)
        )
        self.planner = planner or ConversionPlanner()
        self.executor = executor or PlanExecutor()

    def detect(self, path: Path) -> list[DetectionResult]:
        return [result for result in self.adapters.detect_all(path) if result.confidence > 0]

    def import_library(
        self, path: Path, source_format: str | None = None, options: ImportOptions | None = None
    ) -> tuple[LibraryAdapter, Library]:
        adapter = (
            self.adapters.resolve(source_format) if source_format else self.adapters.detect(path)[0]
        )
        import_options = options or ImportOptions()
        result = adapter.import_library(path, import_options)
        library = result.library
        if import_options.calculate_hashes:
            self._calculate_hashes(library)
        library.diagnostics = validate_library(library, self.adapters.systems)
        return adapter, library

    def convert(
        self,
        source: Path,
        target: Path,
        target_format: str,
        *,
        source_format: str | None = None,
        import_options: ImportOptions | None = None,
        export_options: ExportOptions | None = None,
        dry_run: bool = False,
    ) -> ConversionResult:
        target_adapter = self.adapters.resolve(target_format)
        if target_adapter.name == "savedeck" and (import_options is None or import_options.source_profile is None):
            import_options = (import_options or ImportOptions()).model_copy(update={
                "source_profile": Path(__file__).parents[1] / "profiles/pegasus-g-savedeck.json",
            })
        source_adapter, library = self.import_library(source, source_format, import_options)
        options = export_options or ExportOptions()
        synchronize = source_adapter.name == "pegasus" and target_adapter.name in {"es-de", "savedeck"} and options.rom_mode == RomMode.NONE
        if synchronize:
            existing = {}
            from retrolibx.adapters.savedeck.document import parse_document
            from retrolibx.adapters.savedeck.adapter import ordered_games, platform_directory
            from retrolibx.adapters.esde.merge import parse_xml, relative_game_path
            for system in library.systems:
                name = system.metadata.get("target_system", system.id)
                if target_adapter.name == "savedeck":
                    system.games = ordered_games(system)
                    name = platform_directory(system).as_posix()
                    system.metadata["target_system"] = name
                    path = target / platform_directory(system) / "savedeck.toml"
                    existing[name] = {game["file"].casefold() for game in parse_document(path.read_bytes())["games"]} if path.is_file() else set()
                else:
                    path = target / "gamelists" / name / "gamelist.xml"
                    existing[name] = {relative_game_path(game.findtext("path") or "", system.metadata["source_root"]).removeprefix("./").casefold()
                                      for game in parse_xml(path.read_bytes(), "gameList").findall("game")} if path.is_file() else set()
            select_entries(library, existing, skip_existing=options.conflict != ConflictPolicy.OVERWRITE)
            if any(item.severity == "error" for item in library.diagnostics):
                raise ValidationError("Resolve source library errors before synchronizing entries")
        if options.shared_pegasus and target_adapter.name != "es-de":
            raise ValidationError("--shared-pegasus is only available for ES-DE exports")
        if options.shared_pegasus and options.conflict == ConflictPolicy.RENAME:
            raise ValidationError("Shared media migration requires stable filenames; rename is not supported")
        if options.shared_pegasus and (options.rom_mode != RomMode.NONE or options.media_mode != MediaMode.COPY):
            raise ValidationError("Shared media requires ROM mode none and media mode copy")
        if options.shared_pegasus and any(d.severity == "error" for d in library.diagnostics):
            raise ValidationError("Resolve source library errors before migrating shared media")
        intent = target_adapter.render_library(library, target, options)
        intent.diagnostics.extend(item for item in library.diagnostics if item.severity != "error")
        if target_adapter.name == "savedeck":
            from retrolibx.adapters.savedeck.adapter import platform_directory
            from retrolibx.adapters.savedeck.merge import merge_lists

            source_roots = {}
            for system in library.systems:
                rom = next((rom for game in system.games for rom in game.roms), None)
                root = system.metadata.get("source_root")
                if root is None:
                    root = (rom.path.resolve().parents[len(rom_relative_path(rom.path, rom.metadata).parts) - 1]
                            if rom else library.source_path or source)
                source_roots[platform_directory(system).as_posix()] = Path(root)
            merge_lists(intent, target, source_roots=source_roots, replace=options.conflict == ConflictPolicy.OVERWRITE,
                        valid_files={platform_directory(system).as_posix(): set(system.metadata["valid_rom_paths"])
                                     for system in library.systems} if synchronize else None,
                        source_order={platform_directory(system).as_posix(): system.metadata["valid_rom_paths"]
                                      for system in library.systems} if synchronize else None)
        if target_adapter.name == "es-de":
            rom_roots: dict[str, str] = {}
            for system in library.systems:
                target_name = system.metadata.get("target_system", system.id)
                if options.rom_mode != RomMode.NONE:
                    directory = self.adapters.systems.directory(system.id, "es-de") or system.id
                    rom_root = target.resolve() / "ROMs" / directory
                else:
                    roots: set[Path] = set()
                    for game in system.games:
                        for rom in game.roms:
                            relative = rom_relative_path(rom.path, rom.metadata)
                            roots.add(rom.path.resolve().parents[len(relative.parts) - 1])
                    if len(roots) > 1:
                        raise ValidationError(f"Multiple ROM roots for ES-DE system: {system.id}")
                    rom_root = next(iter(roots), Path(system.metadata.get("source_root") or source.resolve()))
                rom_roots[target_name] = rom_root.as_posix()
            merge_gamelists(intent, target, rom_roots, replace=synchronize and options.conflict == ConflictPolicy.OVERWRITE,
                            skip_existing=synchronize and options.conflict != ConflictPolicy.OVERWRITE,
                            valid_paths={system.metadata.get("target_system", system.id): {"./" + path for path in system.metadata["valid_rom_paths"]}
                                         for system in library.systems} if synchronize else None)
            if options.shared_pegasus:
                prepare_shared_media(
                    library, intent, library.source_path or source,
                    (target.resolve() / "downloaded_media").as_posix(),
                    (import_options or ImportOptions()).metadata_encoding,
                )
        intent.diagnostics.extend(self._loss_report(source_adapter, target_adapter, library))
        plan = self.planner.plan(
            intent,
            source_root=(library.source_path or source) if options.shared_pegasus else source,
            target_root=target,
            source_format=source_adapter.name,
            target_format=target_adapter.name,
            options=options,
        )
        execution = None if dry_run else self.executor.execute(plan)
        return ConversionResult(library=library, plan=plan, execution=execution)

    @staticmethod
    def _calculate_hashes(library: Library) -> None:
        for system in library.systems:
            for game in system.games:
                for rom in game.roms:
                    if not rom.path.is_file():
                        continue
                    crc = 0
                    md5 = hashlib.md5(usedforsecurity=False)
                    sha1 = hashlib.sha1(usedforsecurity=False)
                    size = 0
                    with rom.path.open("rb") as handle:
                        while chunk := handle.read(1024 * 1024):
                            size += len(chunk)
                            crc = zlib.crc32(chunk, crc)
                            md5.update(chunk)
                            sha1.update(chunk)
                    rom.size = size
                    rom.crc32 = f"{crc & 0xFFFFFFFF:08X}"
                    rom.md5 = md5.hexdigest()
                    rom.sha1 = sha1.hexdigest()

    @staticmethod
    def _loss_report(
        source: LibraryAdapter, target: LibraryAdapter, library: Library
    ) -> list[Diagnostic]:
        diagnostics: list[Diagnostic] = []
        labels = {
            "video": "video assets",
            "collections": "collections",
            "favorites": "favorite flags",
            "play_stats": "play statistics",
            "launch_config": "launch configuration",
        }
        for field, label in labels.items():
            if getattr(source.capabilities, field) and not getattr(target.capabilities, field):
                diagnostics.append(
                    Diagnostic(
                        severity="warning",
                        code="potential-data-loss",
                        message=f"Target {target.name} cannot fully represent {label}",
                        details={"field": field},
                    )
                )
        if library.collections and not target.capabilities.collections:
            diagnostics.append(
                Diagnostic(
                    severity="warning",
                    code="potential-data-loss",
                    message=f"Target {target.name} does not support collections",
                )
            )
        return diagnostics
