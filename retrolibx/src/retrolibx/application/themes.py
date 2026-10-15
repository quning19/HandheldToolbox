"""Managed originals, seven existing adaptation profiles, and explicit theme uploads."""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath
import hashlib
import json
import re
import shlex
import subprocess
import uuid
from xml.sax.saxutils import escape
from frontend_platforms import platform_component

from retrolibx.core.executor import PlanExecutor
from retrolibx.core.operations import ExportIntent, FileRequest, TextRequest, WriteManifest
from retrolibx.core.options import ExportOptions
from retrolibx.core.planner import ConversionPlanner
from retrolibx.adapters.esde.merge import parse_xml
from retrolibx.errors import ValidationError

from .desktop import checkpoint, new_job
from .device import AdbReader, AdbUploader
from .platform_catalog import bundled_registry, materialize_catalog

DATA = Path(__file__).with_name("theme_data")
PROFILES = {
    "canvas": "Canvas", "aura": "Aura", "alekfull-nx": "Alekfull NX",
    "elementerial": "Elementerial", "iconic": "Iconic",
    "iisu": "iiSU Interpreted", "playstation-x": "PlayStation-X",
}


@dataclass
class ThemeInfo:
    id: str
    name: str
    original: bool = False
    converted: bool = False
    device: bool | None = None
    source: Path | None = None
    output: Path | None = None
    output_name: str = ""


def json_file(path, default):
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else default


def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)


def definitions_digest(definitions):
    from dataclasses import asdict
    return hashlib.sha256(json.dumps([asdict(item) for item in definitions], ensure_ascii=False,
                                     sort_keys=True).encode("utf-8")).hexdigest()


def theme_identity(name):
    if name.endswith("_天马G"):
        return None
    normalized = re.sub(r"[^a-z0-9]", "", name.casefold())
    aliases = {"iisu": "iisu", "iisuinterpreted": "iisu"}
    return aliases.get(normalized) or next(
        (key for key, value in PROFILES.items() if re.sub(r"[^a-z0-9]", "", value.casefold()) == normalized), None)


def capabilities_name(directory):
    return (parse_xml((directory / "capabilities.xml").read_bytes(), "themeCapabilities").findtext("themeName") or "").strip()


def source_stamp(source):
    stat = (source / "capabilities.xml").stat()
    marker = source / ".frontendtrans-original.json"
    return [stat.st_size, stat.st_mtime_ns, marker.read_text(encoding="utf-8") if marker.is_file() else ""]


def local_themes(workspace, definitions):
    records = json_file(workspace / "config/theme-results.json", {})
    digest = definitions_digest(definitions)
    originals = workspace / "themes/original"
    sources = {}
    if originals.is_dir():
        for directory in sorted(originals.iterdir()):
            if not directory.is_dir() or not (directory / "capabilities.xml").is_file():
                continue
            try:
                identity = theme_identity(capabilities_name(directory))
            except (OSError, ValueError, ValidationError):
                continue
            if identity:
                if identity in sources:
                    raise ValidationError("同一主题发现多份原版，请保留一份：" + PROFILES[identity])
                sources[identity] = directory
    result = []
    for identity, name in PROFILES.items():
        source = sources.get(identity)
        info = ThemeInfo(identity, name, original=source is not None, source=source)
        record = records.get(identity)
        if record and source:
            platform_component(record["directory"])
            output = workspace / "themes/exported" / record["directory"]
            if not output.resolve().is_relative_to((workspace / "themes/exported").resolve()):
                raise ValidationError("主题结果路径超出工作目录")
            info.output = output
            info.output_name = record["directory"]
            info.converted = bool(record.get("complete") and record.get("definitions") == digest
                                  and record.get("source") == source_stamp(source)
                                  and (output / "capabilities.xml").is_file()
                                  and capabilities_name(output) == info.output_name)
        result.append(info)
    return result


def remote_themes(device):
    reader = AdbReader(device.adb, device.serial)
    folder = str(PurePosixPath(device.esde_root) / "themes")
    command = f"""if [ -d {shlex.quote(folder)} ]; then
for dir in {shlex.quote(folder)}/*; do
[ -d "$dir" ] || continue
[ -f "$dir/capabilities.xml" ] || continue
printf '%s\\0' "$dir"
cat "$dir/capabilities.xml"
printf '\\0'
done
fi"""
    fields = reader.read(command).decode("utf-8-sig").split("\0")
    result = []
    for index in range(0, len(fields) - 1, 2):
        path, xml = fields[index:index + 2]
        name = (parse_xml(xml.encode("utf-8"), "themeCapabilities").findtext("themeName") or "").strip()
        result.append((path, name))
    return result


def refresh_themes(workspace, definitions, device, cancelled, progress):
    checkpoint(cancelled)
    result = local_themes(workspace, definitions)
    if device is not None:
        progress("读取设备主题目录与 capabilities.xml…", 30, True)
        remote = remote_themes(device)
        for info in result:
            info.device = any(name == info.output_name or name == info.name + "_天马G"
                              for _path, name in remote)
    return result


def promote(source, destination):
    """Replace only a managed directory; keep the preceding copy recoverable."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.is_symlink() or destination.is_junction():
        raise ValidationError("主题目标不能是链接")
    backup = None
    if destination.exists():
        backup = source.parent / ("previous-" + destination.name + "-" + uuid.uuid4().hex[:8])
        destination.replace(backup)
    try:
        source.replace(destination)
    except OSError:
        if backup is not None:
            backup.replace(destination)
        raise


def sync_originals(workspace, identities, device, cancelled, progress):
    if device is None:
        raise ValidationError("请先在游戏库页面刷新并连接设备。")
    available = remote_themes(device)
    missing = []
    for index, identity in enumerate(identities):
        checkpoint(cancelled)
        matches = [(path, name) for path, name in available if theme_identity(name) == identity]
        if len(matches) != 1:
            missing.append(PROFILES[identity] + ("：设备无原版主题" if not matches else "：有多份原版主题"))
            continue
        remote, _name = matches[0]
        job = new_job(workspace, "theme-sync")
        target = job / "original"
        progress("同步原版：" + PROFILES[identity], int(index * 100 / len(identities)), False)
        # Confirm the serial still belongs to an authorized device before pulling.
        AdbReader(device.adb, device.serial).read("test -d " + shlex.quote(remote))
        subprocess.run([str(device.adb), "-s", device.serial, "pull", remote, str(target)],
                       capture_output=True, check=True, timeout=3600,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if theme_identity(capabilities_name(target)) != identity:
            raise ValidationError("同步的主题类型不匹配：" + PROFILES[identity])
        checkpoint(cancelled)
        save_json(target / ".frontendtrans-original.json", {"synced": datetime.now().isoformat(), "serial": device.serial})
        promote(target, workspace / "themes/original" / identity)
    return {"message": "原版同步结束。" + "；".join(missing)}


def apply_files(intent, source, target):
    plan = ConversionPlanner().plan(intent, source_root=source, target_root=target,
                                    source_format="theme", target_format="theme", options=ExportOptions(conflict="overwrite"))
    plan.operations = [operation for operation in plan.operations if not isinstance(operation, WriteManifest)]
    PlanExecutor().execute(plan)


def adapt_theme(workspace, definitions, info, cancelled, progress):
    from PIL import Image
    from .theme_badges import draw_badge

    if info.source is None:
        raise ValidationError("请先同步原版：" + info.name)
    source = info.source.resolve()
    job = new_job(workspace, "theme-convert")
    destination = job / "complete"
    generated = job / "generated"
    generated.mkdir()
    profile = json_file(DATA / (info.id + ".json"), {})
    batch = json_file(DATA / "rules.json", {})[info.id]
    badge = json_file(DATA / "badge.json", {})
    catalog = job / "platform-config"
    identities = materialize_catalog(definitions, catalog)
    registry = bundled_registry()
    nodes = {node.findtext("name"): node for node in parse_xml((catalog / "es_systems.xml").read_bytes(), "systemList").findall("system")}
    by_identity = {identities[item.id]: item for item in definitions}
    rules = {item["name"]: dict(item) for item in batch["platforms"] if item["name"] in by_identity}
    for item in definitions:
        if (item.parent and item.mode == "separate" and identities[item.id] not in rules
                and identities[item.id] not in registry.records):
            rules[identities[item.id]] = {"name": identities[item.id], "slots": "all"}
    intent = ExportIntent()
    for path in source.rglob("*"):
        if path.is_symlink() or path.is_junction():
            raise ValidationError("原版主题中存在链接：" + str(path))
        if path.is_file() and ".git" not in path.relative_to(source).parts and path.name not in {
            "_build_report.txt", "_verify.txt", "_manifest.json", ".frontendtrans-original.json",
        }:
            intent.files.append(FileRequest(source=path, destination=PurePosixPath(path.relative_to(source).as_posix()), category="media"))
    progress("复制完整原版：" + info.name, 10, False)
    apply_files(intent, source, destination)
    overlay = ExportIntent()
    for index, (identity, rule) in enumerate(rules.items()):
        checkpoint(cancelled)
        definition = by_identity[identity]
        if definition.mode == "inherit" and definition.parent:
            continue
        record = registry.records.get(identity, {})
        theme = nodes[identity].findtext("theme")
        parent = identities[definition.parent] if definition.parent else record.get("base_platform")
        candidates = list(dict.fromkeys(value for value in (
            theme, nodes[parent].findtext("theme") if parent else record.get("base_platform"), rule.get("fallback_source")
        ) if value))
        text = definition.badge or record.get("badge_text")
        slots = batch["slots_all"] if rule["slots"] == "all" else rule["slots"]
        for slot in slots:
            folder = profile["slots"][slot]
            suffixes = profile.get("directory_slots", {}).get(slot, [""])
            extension = profile.get("slot_ext", {}).get(slot, ".webp")
            for suffix in suffixes:
                def asset(name):
                    return source / folder / name / (name + suffix + extension) if slot in profile.get("directory_slots", {}) else source / folder / (name + extension)
                found = next(((asset(name), name) for name in candidates if asset(name).is_file()), None)
                if found is None:
                    if slot in profile.get("required_slots", []):
                        raise ValidationError(f"{info.name} / {definition.name} 缺少必需素材：{slot}{suffix}")
                    continue
                path, used = found
                relative = PurePosixPath(folder) / theme / (theme + suffix + extension) if slot in profile.get("directory_slots", {}) else PurePosixPath(folder) / (theme + extension)
                if text and used != theme and extension not in {".svg", ".mp4"} and slot in profile.get("badge_slots", []) and suffix not in profile.get("copy_only_suffixes", {}).get(slot, []):
                    params = dict(badge["default"])
                    params.update(next(candidate for candidate in badge["candidates"] if candidate["name"] == badge["active_candidate"]))
                    params.update(badge.get("slot_overrides", {}).get(slot, {}))
                    params["text"] = text
                    with Image.open(path) as image:
                        output = draw_badge(image, params, badge)
                        generated_path = generated / (uuid.uuid4().hex + extension)
                        output.convert("RGB" if extension in {".jpg", ".jpeg"} else "RGBA").save(generated_path)
                    path = generated_path
                overlay.files.append(FileRequest(source=path, destination=relative, category="media"))
        directories = [(profile.get("metadata_dir"), True)] + [(value, False) for value in profile.get("metadata_copy_dirs", [])]
        for folder, required in directories:
            if not folder:
                continue
            origin = next((source / folder / (name + ".xml") for name in candidates if (source / folder / (name + ".xml")).is_file()), None)
            if origin is None and required:
                origin = source / folder / "_default.xml"
            if origin is None:
                continue
            xml = origin.read_text(encoding="utf-8-sig")
            label = escape(definition.name)
            if "<systemName>" in xml:
                xml = re.sub(r"<systemName>.*?</systemName>", lambda _match: "<systemName>" + label + "</systemName>", xml, count=1, flags=re.S)
            else:
                xml = xml.replace("</system>", "    <systemName>" + label + "</systemName>\n</system>")
            overlay.texts.append(TextRequest(destination=PurePosixPath(folder) / (theme + ".xml"), content=xml))
        progress(f"{info.name}：适配 {definition.name}", 20 + int((index + 1) * 60 / max(1, len(rules))), True)
    checkpoint(cancelled)
    apply_files(overlay, job, destination)
    name = capabilities_name(source) + "_天马G"
    platform_component(name)
    xml = (destination / "capabilities.xml").read_text(encoding="utf-8-sig")
    xml = re.sub(r"<themeName>.*?</themeName>", lambda _match: "<themeName>" + escape(name) + "</themeName>", xml, count=1, flags=re.S)
    # Retain the established Android cover/cart aspect-ratio adjustment.
    for android in destination.rglob("androidgames.xml"):
        switch = android.with_name("switch.xml")
        if switch.is_file():
            current, reference = android.read_text(encoding="utf-8-sig"), switch.read_text(encoding="utf-8-sig")
            for tag in ("systemCoverSize", "systemCartSize"):
                match = re.search(r"<%s>(.*?)</%s>" % (tag, tag), reference, re.S)
                if match:
                    current = re.sub(r"<%s>.*?</%s>" % (tag, tag), lambda _m: f"<{tag}>{match.group(1)}</{tag}>", current, count=1, flags=re.S)
            android.write_text(current, encoding="utf-8")
    apply_files(ExportIntent(texts=[TextRequest(destination=PurePosixPath("capabilities.xml"), content=xml)]), source, destination)
    checkpoint(cancelled)
    progress("保存完整主题：" + name, 95, False)
    promote(destination, workspace / "themes/exported" / name)
    records_path = workspace / "config/theme-results.json"
    records = json_file(records_path, {})
    records[info.id] = {"directory": name, "complete": True, "definitions": definitions_digest(definitions),
                        "source": source_stamp(source), "generated": datetime.now().isoformat()}
    save_json(records_path, records)


def run_themes(operation, workspace, definitions, identities, device, cancelled, progress):
    if operation == "refresh":
        return refresh_themes(workspace, definitions, device, cancelled, progress)
    if operation == "sync":
        result = sync_originals(workspace, identities, device, cancelled, progress)
        return {"themes": local_themes(workspace, definitions), "message": result["message"]}
    infos = {info.id: info for info in local_themes(workspace, definitions)}
    if operation == "convert":
        for identity in identities:
            checkpoint(cancelled)
            adapt_theme(workspace, definitions, infos[identity], cancelled, progress)
        return {"themes": local_themes(workspace, definitions), "message": "主题转换完成。"}
    if operation != "upload" or device is None:
        raise ValidationError("请先连接设备。")
    for index, identity in enumerate(identities):
        checkpoint(cancelled)
        info = infos[identity]
        if not info.converted or info.output is None:
            raise ValidationError("转换结果缺失或已过期，请重新转换：" + info.name)
        progress("上传完整主题：" + info.name, int(index * 100 / len(identities)), False)
        AdbUploader(device.adb, device.serial).upload(
            info.output, str(PurePosixPath(device.esde_root) / "themes" / info.output_name))
    return {"themes": refresh_themes(workspace, definitions, device, cancelled, progress),
            "message": "主题上传完成，设备状态已刷新。"}

