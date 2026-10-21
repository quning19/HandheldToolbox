"""SaveDeck config/media workflows sharing the original ROMs, without Qt."""

from dataclasses import dataclass, field
import hashlib
from pathlib import Path, PurePosixPath

from frontend_common.jobs import checkpoint, new_job
from frontend_common.files import write_json
from frontend_devices.adb import AdbReader, capture_pegasus_source
from frontend_devices.discovery import Device
from frontend_platforms.catalog import materialize_catalog
from retrolibx.adapters.savedeck.adapter import ordered_games
from retrolibx.adapters.savedeck.document import apply_source_order, merge_documents, parse_document, render_document
from retrolibx.adapters.savedeck.merge import filter_missing_roms
from retrolibx.application.service import ConversionService
from retrolibx.core.models import Library
from retrolibx.core.entries import select_entries
from retrolibx.core.operations import ExportIntent, FileRequest, TextRequest
from retrolibx.core.options import ExportOptions, ImportOptions
from retrolibx.errors import RetroLibXError, ValidationError
from retrolibx.utils.discovery import find_metadata

from .desktop import PlatformInfo
from .publication import AdbPublisher


@dataclass
class SaveDeckSession:
    source: Path
    target: Path
    config_dir: Path
    remote_root: str = ""
    device: Device | None = None
    platforms: dict[str, PlatformInfo] = field(default_factory=dict)
    libraries: dict[str, Library] = field(default_factory=dict)
    baselines: dict[str, bytes | None] = field(default_factory=dict)
    cancelled: bool = False


def _digest(raw: bytes | None) -> str:
    return hashlib.sha256(raw).hexdigest() if raw is not None else ""


def scan_savedeck(workspace, definitions, source, device, cancelled, progress, emit_platform):
    job = new_job(workspace, "savedeck-scan")
    config_dir = job / "platform-config"
    identities = materialize_catalog(definitions, config_dir)
    service = ConversionService(platform_config_dir=config_dir)
    checkpoint(cancelled)
    if device:
        progress("读取天马配置、SaveDeck 配置与文件名，不下载 ROM 或媒体…", 0, True)
        root = job / "source"
        platforms = capture_pegasus_source(AdbReader(device.adb, device.serial, temporary_root=job), source, root)
    else:
        root = Path(source).resolve()
        if not root.is_dir():
            raise ValidationError("天马 G 目录不存在。")
        if workspace.resolve().is_relative_to(root):
            raise ValidationError("软件工作目录不能位于所选 ROM 目录内。")
        platforms = [path.parent.relative_to(root).as_posix() for path in find_metadata(root, ("metadata.pegasus.txt",))]
    if not platforms:
        raise ValidationError("所选目录没有 metadata.pegasus.txt。")
    session = SaveDeckSession(root, root, config_dir, source if device else "", device)
    by_identity = {identity: next(item for item in definitions if item.id == key) for key, identity in identities.items()}
    for index, platform in enumerate(platforms):
        if cancelled():
            session.cancelled = True
            break
        info = PlatformInfo(platform, platform, "", 0, 0, 0)
        try:
            _, library = service.import_library(root, "pegasus", ImportOptions(
                platforms=[platform], metadata_encoding="auto",
                device_rom_root=source if device else None,
                source_profile=Path(__file__).parents[1] / "retrolibx/profiles/pegasus-g-savedeck.json"))
            session.libraries[platform] = library
            selection = select_entries(library)
            system = library.systems[0]
            definition = by_identity.get(system.id)
            record = service.adapters.systems.records.get(system.id)
            info.name = definition.name if definition else system.name
            info.art = (record.theme if record else "") or ""
            info.roms = sum(rom.path.is_file() for game in system.games for rom in game.roms)
            info.covers = sum(sum(rom.path.is_file() for rom in game.roms) for game in system.games
                              if game.media.box_front and game.media.box_front.is_file())
            config = root / platform / "savedeck.toml"
            raw = config.read_bytes() if config.is_file() else None
            session.baselines[platform] = raw
            old = parse_document(raw) if raw is not None else {"games": []}
            old_files = {entry["file"].casefold() for entry in old["games"]}
            info.existing = sum(rom.path.relative_to(root / platform).as_posix().casefold() in old_files
                                for game in system.games for rom in game.roms if rom.path.is_file())
            errors = [item.message for item in library.diagnostics
                      if item.severity == "error" and item.code != "missing-rom"]
            info.missing_references = selection["missing"]
            # Rendering only checks representability of fields needed for this export.
            service.adapters.resolve("savedeck").render_library(library, job / "preview", ExportOptions(rom_mode="none"))
            if errors:
                info.error = "；".join(errors)
        except (OSError, ValueError, RetroLibXError) as exc:
            info.error = str(exc)
        session.platforms[platform] = info
        emit_platform(info)
        progress(f"已加载 {index + 1}/{len(platforms)} 个平台", int((index + 1) * 100 / len(platforms)), True)
    return session


def convert_savedeck(session, platforms, shared, full, workspace, cancelled, progress):
    if shared:
        raise ValidationError("SaveDeck 已直接共用原媒体，不使用 ES-DE 共用素材迁移。")
    if not platforms or set(platforms) - session.platforms.keys():
        raise ValidationError("请重新加载并选择平台。")
    platforms = list(dict.fromkeys(platforms))
    errors = [session.platforms[name].error for name in platforms if session.platforms[name].error]
    if errors:
        raise ValidationError("；".join(errors))
    service = ConversionService(platform_config_dir=session.config_dir)
    job = new_job(workspace, "savedeck-export")
    stage = job / "files"
    intent = ExportIntent()
    count = 0
    removed = 0
    metadata_guards = {}
    for platform in platforms:
        checkpoint(cancelled)
        library = session.libraries[platform].model_copy(deep=True)
        intent.diagnostics.extend(item for item in library.diagnostics if item.severity != "error")
        system = library.systems[0]
        metadata_guards[platform] = system.metadata["metadata_sha256"]
        if not session.device:
            current = (session.source / platform / "metadata.pegasus.txt").read_bytes()
            if _digest(current) != metadata_guards[platform]:
                raise ValidationError(f"天马配置已变化，请重新加载：{platform}")
        baseline = session.baselines[platform]
        old = parse_document(baseline) if baseline is not None else None
        system.games = ordered_games(system)
        selection = select_entries(library, {system.id: {game["file"].casefold() for game in old["games"]} if old else set()},
                                   skip_existing=not full)
        rendered = service.adapters.resolve("savedeck").render_library(library, stage, ExportOptions(rom_mode="none"))
        data = parse_document(rendered.texts[0].content.encode("utf-8"))
        if baseline is not None:
            data = merge_documents(old, data, replace=full, valid_files=set(system.metadata["valid_rom_paths"]))
        intent.diagnostics.extend(rendered.diagnostics)
        data = filter_missing_roms(data, session.source / platform, intent.diagnostics)
        data = apply_source_order(data, system.metadata["valid_rom_paths"])
        count += selection["selected"]
        removed += selection["removed"]
        intent.texts.append(TextRequest(destination=PurePosixPath(platform) / "savedeck.toml", content=render_document(data)))
        rendered_directory = rendered.texts[0].destination.parent
        intent.files.extend(FileRequest(source=request.source,
                            destination=PurePosixPath(platform) / request.destination.relative_to(rendered_directory),
                            category="media") for request in rendered.files)
    progress("生成 SaveDeck 配置…", 35, True)
    stage_intent = intent.model_copy(update={"files": []}) if session.device else intent
    plan = service.planner.plan(stage_intent, source_root=session.source, target_root=stage,
                                source_format="pegasus", target_format="savedeck", options=ExportOptions(rom_mode="none"))
    (job / "plan.json").write_text(plan.model_dump_json(indent=2), encoding="utf-8")
    service.executor.execute(plan)
    if session.device:
        write_json(job / "media-plan.json", {"serial": session.device.serial, "copies": [
            {"source": str(PurePosixPath(session.remote_root) / request.source.relative_to(session.source).as_posix()),
             "destination": str(PurePosixPath(session.remote_root) / request.destination)}
            for request in intent.files]})
    checkpoint(cancelled)
    progress("备份并发布 SaveDeck 配置…", 65, False)
    if session.device:
        publisher = AdbPublisher(session.device.adb, session.device.serial, temporary_root=job)
        # Capture all config baselines before device media copies and publication.
        for platform in platforms:
            remote = PurePosixPath(session.remote_root) / platform
            if publisher._digest(str(remote / "metadata.pegasus.txt")) != metadata_guards[platform]:
                raise ValidationError(f"设备天马配置已变化，请重新加载：{platform}")
            if publisher._digest(str(remote / "savedeck.toml")) != _digest(session.baselines[platform]):
                raise ValidationError(f"设备 SaveDeck 配置已变化，请重新加载：{platform}")
        for platform in platforms:
            remote = PurePosixPath(session.remote_root) / platform / "savedeck.toml"
            publisher.copy_media([
                (str(PurePosixPath(session.remote_root) / request.source.relative_to(session.source).as_posix()),
                 str(PurePosixPath(session.remote_root) / request.destination))
                for request in intent.files if request.destination.parent.is_relative_to(PurePosixPath(platform))], overwrite=full)
            publisher.publish_config(stage / platform / "savedeck.toml", str(remote), _digest(session.baselines[platform]))
        output = session.remote_root
    else:
        for platform in platforms:
            if _digest((session.source / platform / "metadata.pegasus.txt").read_bytes()) != metadata_guards[platform]:
                raise ValidationError(f"天马配置已变化，请重新加载：{platform}")
        publish = ExportIntent(texts=[TextRequest(
            destination=request.destination, content=request.content,
            expected_sha256=_digest(session.baselines[request.destination.parent.as_posix()]), backup=True,
        ) for request in intent.texts], files=[
            FileRequest(source=stage.joinpath(*request.destination.parts), destination=request.destination, category="media")
            for request in intent.files
            if request.source.resolve() != session.source.joinpath(*request.destination.parts).resolve()
        ])
        publication = service.planner.plan(publish, source_root=stage, target_root=session.source,
                                           source_format="savedeck-export", target_format="savedeck", options=ExportOptions(rom_mode="none", conflict="overwrite" if full else "skip"))
        # Keep the manifest in the job; publish selected media and configs only.
        publication.operations = [operation for operation in publication.operations if operation.kind != "write_manifest"]
        service.executor.execute(publication)
        output = str(session.source)
    return {"roms": count, "removed": removed, "output": output, "export": str(stage),
            "warnings": [item.message for item in intent.diagnostics]}
