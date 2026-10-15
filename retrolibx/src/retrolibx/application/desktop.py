"""Desktop use cases. No Qt dependency, example data, or fixed device serials."""

from dataclasses import dataclass, field
from copy import deepcopy
from datetime import datetime
from pathlib import Path, PurePosixPath
import hashlib
import json
import os
import shlex
import shutil
import subprocess
import sys
import uuid

from frontend_platforms import platform_configuration
from retrolibx.adapters.esde.merge import merge_gamelists, parse_xml, xml_text
from retrolibx.core.operations import TextRequest
from retrolibx.core.options import ExportOptions, ImportOptions
from retrolibx.errors import ValidationError
from retrolibx.utils.discovery import find_metadata, rom_relative_path

from .device import AdbReader, capture_device
from .deployment import deploy_task
from .handheld import HandheldConfig, _reuse_systems, build_handheld
from .platform_catalog import materialize_catalog
from .publication import AdbPublisher
from .selection import detect_metadata_encoding, existing_paths, select_entries, track_files
from .service import ConversionService
from .shared_media import prepare_shared_media


class Cancelled(Exception):
    pass


def checkpoint(cancelled) -> None:
    if cancelled():
        raise Cancelled("已取消操作；已经写入的文件保留。")


def new_job(workspace: Path, kind: str) -> Path:
    path = workspace / "temp" / (kind + "-" + datetime.now().strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:8])
    path.mkdir(parents=True, exist_ok=False)
    return path


def local_target(workspace: Path, source: str | Path) -> Path:
    root = Path(source).resolve()
    key = hashlib.sha256(str(root).casefold().encode("utf-8")).hexdigest()[:10]
    return workspace / "library" / ((root.name or "library") + "-" + key) / "ES-DE"


def find_adb() -> Path:
    found = shutil.which("adb")
    if found:
        return Path(found)
    candidates = [
        Path(os.environ.get("ANDROID_HOME", ".")) / "platform-tools/adb.exe",
        Path(os.environ.get("ANDROID_SDK_ROOT", ".")) / "platform-tools/adb.exe",
        Path(os.environ.get("LOCALAPPDATA", ".")) / "Android/Sdk/platform-tools/adb.exe",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise ValidationError("未找到 ADB。请安装 Android platform-tools 并加入 PATH。")


@dataclass(frozen=True)
class Device:
    adb: Path
    serial: str
    label: str
    esde_root: str
    roots: tuple[tuple[str, int, str], ...]


def mumu_endpoints() -> list[str]:
    """Ask the running MuMu installation for its active local ADB ports."""
    if sys.platform != "win32":
        return []
    powershell = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32/WindowsPowerShell/v1.0/powershell.exe"
    command = (
        "[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false); "
        "Get-Process -Name MuMuNxMain -ErrorAction SilentlyContinue | "
        "ForEach-Object { $_.Path }; exit 0"
    )
    try:
        result = subprocess.run(
            [str(powershell), "-NoProfile", "-NonInteractive", "-Command", command],
            capture_output=True, check=True, timeout=10,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        managers = {
            Path(line.strip()).with_name("MuMuManager.exe")
            for line in result.stdout.decode("utf-8-sig").splitlines() if line.strip()
        }
        endpoints = set()
        for manager in sorted(managers):
            if not manager.is_file():
                continue
            result = subprocess.run(
                [str(manager), "info", "--vmindex", "all"],
                capture_output=True, check=True, timeout=10,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            instances = json.loads(result.stdout.decode("utf-8-sig"))
            if not isinstance(instances, dict):
                raise ValueError("MuMu 实例信息格式无效")
            for instance in instances.values():
                if not isinstance(instance, dict):
                    continue
                if instance.get("is_process_started") is not True or instance.get("is_android_started") is not True:
                    continue
                host, port = instance.get("adb_host_ip"), instance.get("adb_port")
                if isinstance(host, str) and host in {"127.0.0.1", "localhost"} and type(port) is int and 1 <= port <= 65535:
                    endpoints.add(f"127.0.0.1:{port}")
        return sorted(endpoints)
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        raise ValidationError(f"无法读取 MuMu 连接信息，请确认模拟器已启动：{exc}") from exc


def adb_device_rows(adb: Path) -> list[list[str]]:
    result = subprocess.run([str(adb), "devices", "-l"], capture_output=True, check=True, timeout=20,
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return [parts for line in result.stdout.decode("utf-8").splitlines()
            if len(parts := line.split()) > 1 and parts[1] in {"device", "offline", "unauthorized"}]


def discover_device() -> Device:
    adb = find_adb()
    rows = adb_device_rows(adb)
    connection_errors = []
    if not any(parts[1] in {"device", "unauthorized"} for parts in rows):
        endpoints = mumu_endpoints()
        for endpoint in endpoints:
            try:
                result = subprocess.run(
                    [str(adb), "connect", endpoint], capture_output=True, check=True, timeout=5,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                message = result.stdout.decode("utf-8", errors="replace").strip()
                if "connected to" not in message:
                    connection_errors.append(message or endpoint)
            except (OSError, subprocess.SubprocessError) as exc:
                connection_errors.append(f"{endpoint}: {exc}")
        if endpoints:
            rows = adb_device_rows(adb)
    authorized = [parts for parts in rows if parts[1] == "device"]
    if not authorized:
        if any(parts[1] == "unauthorized" for parts in rows):
            raise ValidationError("设备尚未授权，请在设备上允许 USB 调试后刷新。")
        detail = "；".join(connection_errors)
        raise ValidationError("未找到在线设备。请连接掌机或等待 MuMu 安卓系统启动后刷新。"
                              + (f" MuMu 连接失败：{detail}" if detail else ""))
    if len(authorized) > 1:
        raise ValidationError("多台设备在线，请先断开其他设备后刷新：" + "、".join(parts[0] for parts in authorized))
    parts = authorized[0]
    serial = parts[0]
    label = next((part[6:] for part in parts[2:] if part.startswith("model:")), serial)
    reader = AdbReader(adb, serial)
    # Root discovery counts immediate child directories only.
    script = """for base in /storage/emulated/0 /storage/*; do
case "$base" in /storage/emulated|/storage/self) continue;; esac
[ -d "$base" ] || continue
for dir in "$base"/*; do
[ -d "$dir" ] || continue
name=$(basename "$dir")
case "$name" in [Rr][Oo][Mm]|[Rr][Oo][Mm][Ss])
count=0
for child in "$dir"/*; do [ ! -d "$child" ] || count=$((count+1)); done
printf '%s\\0%s\\0' "$dir" "$count";; esac
done
done"""
    fields = reader.read(script).decode("utf-8").split("\0")
    roots = {}
    for index in range(0, len(fields) - 1, 2):
        path, count = fields[index:index + 2]
        roots[path] = (path, int(count), "内置存储" if path.startswith("/storage/emulated/0/") else "SD 卡")
    candidates = reader.read("""for dir in /storage/emulated/0/*; do
[ -d "$dir" ] || continue
name=$(basename "$dir")
case "$name" in [Ee][Ss]-[Dd][Ee]) printf '%s\\0' "$dir";; esac
done""").decode("utf-8").strip("\0").split("\0")
    candidates = [path for path in candidates if path]
    if len(candidates) > 1:
        raise ValidationError("内置存储发现多个 ES-DE 目录，请保留唯一工作目录后刷新设备。")
    return Device(adb, serial, label, candidates[0] if candidates else "/storage/emulated/0/ES-DE", tuple(roots.values()))


@dataclass
class PlatformInfo:
    id: str
    name: str
    art: str
    roms: int
    covers: int
    existing: int
    missing_references: int = 0
    unlinked: int = 0
    error: str = ""


@dataclass
class LibrarySession:
    source: Path
    target: Path
    config_dir: Path
    source_key: str
    device: Device | None = None
    remote_root: str = ""
    capture: Path | None = None
    platforms: dict[str, PlatformInfo] = field(default_factory=dict)
    media_path_aliases: dict[str, dict[str, Path]] = field(default_factory=dict)
    cancelled: bool = False


def metadata_encoding(path: Path) -> str:
    return detect_metadata_encoding(path.read_bytes())


def scan_library(workspace, definitions, source, device, cancelled, progress, emit_platform):
    job = new_job(workspace, "scan")
    config_dir = job / "platform-config"
    identities = materialize_catalog(definitions, config_dir)
    service = ConversionService(platform_config_dir=config_dir)
    checkpoint(cancelled)
    if device:
        reader = AdbReader(device.adb, device.serial, temporary_root=job)
        progress("读取平台目录…", 0, True)
        names = reader.read(f"find {shlex.quote(source)} -type f -name metadata.pegasus.txt").decode("utf-8").splitlines()
        platforms = sorted({str(PurePosixPath(name).parent.relative_to(PurePosixPath(source))) for name in names})
        if not platforms:
            raise ValidationError("所选目录没有 metadata.pegasus.txt。")
        checkpoint(cancelled)
        capture = job / "capture"
        progress("批量读取 ROM 索引、metadata 和现有 ES-DE 配置…", 5, True)
        capture_device(reader, source, platforms, device.esde_root, capture,
                       include_disc_descriptors=True, include_shared_media=True)
        session = LibrarySession(capture / "Roms", capture / "snapshot", config_dir,
                                 device.serial + ":" + source, device, source, capture)
        session.media_path_aliases = HandheldConfig.load(capture / "config.json").media_path_aliases
    else:
        root = Path(source).resolve()
        if not root.is_dir():
            raise ValidationError("天马 G 目录不存在。")
        if workspace.resolve().is_relative_to(root):
            raise ValidationError("软件工作目录不能位于所选 ROM 目录内，请在设置中更换工作目录。")
        platforms = [path.parent.relative_to(root).as_posix() for path in find_metadata(root, ("metadata.pegasus.txt",))]
        session = LibrarySession(root, local_target(workspace, root), config_dir, str(root))
    if not platforms:
        raise ValidationError("所选目录没有 metadata.pegasus.txt。")
    by_identity = {identity: next(item for item in definitions if item.id == key)
                   for key, identity in identities.items()}
    for index, platform in enumerate(platforms):
        if cancelled():
            session.cancelled = True
            break
        info = PlatformInfo(platform, platform, "", 0, 0, 0)
        try:
            encoding = metadata_encoding(session.source / platform / "metadata.pegasus.txt")
            _, library = service.import_library(session.source, "pegasus", ImportOptions(
                platforms=[platform], metadata_encoding=encoding,
                media_path_aliases=session.media_path_aliases,
                shared_media_root=None if device else session.target / "downloaded_media",
                source_profile=Path(__file__).parents[1] / "profiles/pegasus-g.json"))
            system = library.systems[0]
            record = service.adapters.systems.records.get(system.id)
            definition = by_identity.get(system.id)
            info.name = definition.name if definition else Path(platform).name
            art_record = record
            if definition and definition.parent:
                art_record = service.adapters.systems.records.get(identities.get(definition.parent), record)
            info.art = (record.theme if record else "") or ""
            art_dir = Path(__file__).parents[1] / "gui/assets/platforms"
            if not (art_dir / (info.art + ".webp")).is_file():
                info.art = (art_record.theme if art_record else "") or ""
            rom_root = str(PurePosixPath(source) / platform) if device else str((session.source / platform).resolve())
            if device:
                config = HandheldConfig(source_root=session.source, device_rom_root=source,
                                        esde_root=device.esde_root, target_snapshot=session.target,
                                        platform_config_dir=config_dir)
                _reuse_systems(config, library, session.target)
            target_name = system.metadata.get("target_system", system.id)
            old = existing_paths(session.target, target_name, rom_root)
            subordinate = track_files([rom.path for game in system.games for rom in game.roms])
            known = set()
            for game in system.games:
                for rom in game.roms:
                    known.add(rom.path.resolve())
                    if not rom.path.is_file():
                        info.missing_references += 1
                        continue
                    if rom.path.resolve() in subordinate:
                        continue
                    info.roms += 1
                    info.covers += bool(game.media.box_front and game.media.box_front.is_file())
                    info.existing += ("./" + rom_relative_path(rom.path, rom.metadata).as_posix()) in old
            if record:
                extensions = {"." + value for value in record.extensions}
                info.unlinked = sum(1 for path in (session.source / platform).rglob("*")
                                    if path.is_file() and path.suffix.casefold() in extensions
                                    and path.resolve() not in known | subordinate
                                    and "media" not in {part.casefold() for part in path.relative_to(session.source / platform).parts}
                                    and not any((parent / "metadata.pegasus.txt").is_file()
                                                for parent in path.parents if parent != (session.source / platform).resolve()
                                                and parent.is_relative_to((session.source / platform).resolve())))
            if record is None:
                info.error = "未识别平台，请在设置的平台管理中添加。"
            errors = [d.message for d in library.diagnostics if d.severity == "error" and d.code != "missing-rom"]
            if errors:
                info.error = "；".join(errors)
        except Exception as exc:
            info.error = str(exc)
        session.platforms[platform] = info
        emit_platform(info)
        progress(f"已检测 {index + 1}/{len(platforms)} 个平台", int((index + 1) * 100 / len(platforms)), True)
    return session


def convert_library(session, platforms, shared, full, workspace, cancelled, progress):
    if not platforms:
        raise ValidationError("请先选择平台。")
    errors = [session.platforms[name].error for name in platforms if session.platforms[name].error]
    if errors:
        raise ValidationError("；".join(errors))
    encoding = "auto"
    checkpoint(cancelled)
    job = new_job(workspace, "convert")
    progress("生成转换计划…", 10, True)
    if session.device:
        config = HandheldConfig.load(session.capture / "config.json")
        config.platform_config_dir = session.config_dir
        config.encoding = encoding
        config.existing_roms_only = True
        config.existing_entries = "replace" if full else "skip"
        config.shared_pegasus = shared
        config.versioned_backups = True
        # GBA vib uses its established metadata-derived Android launch rule.
        service = ConversionService(platform_config_dir=session.config_dir)
        config.metadata_launch_systems = ["GBA vib"] if any(
            (record := service.adapters.systems.resolve(Path(name).name)) and record.id == "GBA vib"
            for name in platforms) else []
        summary = build_handheld(config, platforms, job / "task")
        if not summary["executable"]:
            raise ValidationError("；".join(summary["errors"]))
        checkpoint(cancelled)
        progress("正在设备上复制素材并发布列表与系统配置，请等待…", 45, False)
        remote = "/data/local/tmp/frontendtrans-" + job.name + ".sh"
        deploy_task(AdbPublisher(session.device.adb, session.device.serial, temporary_root=job), job / "task", remote)
        return {"roms": summary["roms"], "output": str(job / "task")}
    service = ConversionService(platform_config_dir=session.config_dir)
    _, library = service.import_library(session.source, "pegasus", ImportOptions(
        platforms=platforms, metadata_encoding=encoding,
        shared_media_root=session.target / "downloaded_media",
        source_profile=Path(__file__).parents[1] / "profiles/pegasus-g.json"))
    roots = {system.id: str(Path(system.metadata["source_root"])) for system in library.systems}
    selection = select_entries(library, session.target, roots,
                               policy="replace" if full else "skip", existing_only=True)
    errors = [item.message for item in library.diagnostics if item.severity == "error"]
    if errors:
        raise ValidationError("；".join(errors))
    options = ExportOptions(rom_mode="none", conflict="overwrite" if full else "skip", shared_pegasus=shared)
    intent = service.adapters.resolve("es-de").render_library(library, session.target, options)
    merge_gamelists(intent, session.target, roots)
    documents = platform_configuration(session.config_dir)
    old = session.target / "custom_systems/es_systems.xml"
    template = parse_xml(documents["es_systems.xml"].encode("utf-8"), "systemList")
    root = parse_xml(old.read_bytes(), "systemList") if old.is_file() else deepcopy(template)
    for node in template.findall("system"):
        if not any(entry.findtext("name") == node.findtext("name") for entry in root.findall("system")):
            root.append(deepcopy(node))
    for system in library.systems:
        node = next(entry for entry in root.findall("system") if entry.findtext("name") == system.id)
        node.find("path").text = roots[system.id].replace("\\", "/")
    documents["es_systems.xml"] = xml_text(root)
    for name, text in documents.items():
        path = session.target / "custom_systems" / name
        raw = path.read_bytes() if path.is_file() else None
        if raw is not None and name != "es_systems.xml":
            text = raw.decode("utf-8")
        intent.texts.append(TextRequest(destination=PurePosixPath("custom_systems") / name, content=text,
                                       expected_sha256=hashlib.sha256(raw).hexdigest() if raw is not None else "", backup=True))
    if shared:
        prepare_shared_media(library, intent, session.source, (session.target / "downloaded_media").as_posix(), encoding)
    plan = service.planner.plan(intent, source_root=session.source, target_root=session.target,
                                source_format="pegasus", target_format="es-de", options=options)
    (job / "plan.json").write_text(plan.model_dump_json(indent=2), encoding="utf-8")
    checkpoint(cancelled)
    progress("正在复制素材并保存列表与完整系统配置…", 50, False)
    service.executor.execute(plan)
    return {"roms": selection["selected"], "output": str(session.target)}

