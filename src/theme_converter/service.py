"""Dynamic managed originals, generic ES-DE adaptation and explicit uploads."""
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath
import hashlib
import json
import re
import shlex
import subprocess
import uuid
from lxml import etree

from frontend_common.files import write_json as save_json
from frontend_common.jobs import checkpoint, new_job
from frontend_devices.adb import AdbReader, AdbUploader
from frontend_platforms import platform_component
from retrolibx.adapters.esde.merge import parse_xml
from retrolibx.core.executor import PlanExecutor
from retrolibx.core.operations import ExportIntent, FileRequest, TextRequest, WriteManifest
from retrolibx.core.options import ExportOptions
from retrolibx.core.planner import ConversionPlanner
from retrolibx.errors import ValidationError
from .parser import ThemeParser, PARSER_VERSION, POLICY_VERSION
from .state import source_index, fingerprint, dependencies, bindings, IGNORED


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
    stale: bool = False
    reason: str = ""
    remote_path: str = ""


def json_file(path, default):
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else default


def theme_identity(name):
    stem = re.sub(r"[^a-z0-9-]+", "-", name.casefold()).strip("-")[:48] or "theme"
    return stem + "-" + hashlib.sha256(name.encode("utf-8")).hexdigest()[:10]


def capabilities_name(directory):
    return (parse_xml((directory / "capabilities.xml").read_bytes(), "themeCapabilities").findtext("themeName") or directory.name).strip()


def local_themes(workspace, definitions):
    records = json_file(workspace / "config/theme-results.json", {})
    deps = dependencies(definitions)
    originals = workspace / "themes/original"
    result = []
    if not originals.is_dir():
        return result
    for directory in sorted(originals.iterdir()):
        if not directory.is_dir() or not (directory / "capabilities.xml").is_file():
            continue
        platform_component(directory.name)
        info = ThemeInfo(directory.name, directory.name, original=True, source=directory)
        try:
            info.name = capabilities_name(directory)
            record = records.get(info.id, {})
            if record.get("last_error"):
                info.reason = record["last_error"]
            if record.get("directory"):
                platform_component(record["directory"])
                info.output_name = record["directory"]
                info.output = workspace / "themes/exported" / info.output_name
                reasons = []
                if record.get("parser") != PARSER_VERSION or record.get("policy") != POLICY_VERSION:
                    reasons.append("解析或素材规则已更新")
                if record.get("dependencies") != deps:
                    reasons.append("相关平台定义已改变")
                if record.get("source_index") != source_index(directory):
                    reasons.append("原版主题文件已改变")
                if record.get("last_error"):
                    reasons.append(record["last_error"])
                if not (info.output / "capabilities.xml").is_file():
                    reasons.append("结果文件缺失")
                elif capabilities_name(info.output) != info.output_name:
                    reasons.append("结果描述与生成记录不一致")
                elif record.get("output_index") != source_index(info.output):
                    reasons.append("导出结果已改变或有文件缺失")
                info.reason = "；".join(reasons)
                info.stale = bool(reasons)
                info.converted = bool(record.get("complete") and not reasons)
        except (OSError, ValueError, ValidationError) as exc:
            info.reason = str(exc)
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
        name = (parse_xml(xml.encode("utf-8"), "themeCapabilities").findtext("themeName") or PurePosixPath(path).name).strip()
        result.append((path, name))
    return result


def refresh_themes(workspace, definitions, device, cancelled, progress):
    checkpoint(cancelled)
    result = local_themes(workspace, definitions)
    if device is None:
        return result
    progress("读取设备主题目录与描述信息…", 30, True)
    remote = remote_themes(device)
    for info in result:
        info.device = any(name == (info.output_name or info.name + "_天马G") for _path, name in remote)
    for path, name in remote:
        if name.endswith("_天马G") or PurePosixPath(path).name.endswith("_天马G"):
            if not any(info.output_name == name or info.name + "_天马G" == name for info in result):
                result.append(ThemeInfo("device-only-" + theme_identity(path), name, device=True,
                                        reason="设备上的适配主题；本地没有对应原版和生成记录。"))
            continue
        marker_matches = []
        for info in result:
            if info.source:
                marker = json_file(info.source / ".frontendtrans-original.json", {})
                if marker.get("remote_directory") == PurePosixPath(path).name:
                    marker_matches.append(info)
        matches = marker_matches or [info for info in result if info.name == name and info.source]
        if len(matches) == 1:
            matches[0].remote_path = path
        else:
            identity = theme_identity(PurePosixPath(path).name)
            result.append(ThemeInfo(identity, name, device=False, remote_path=path))
    return result


def promote(source, destination, workspace):
    """Atomic promotion; old copies and their receipts are durable recovery data."""
    managed = (workspace / "themes").resolve()
    if not managed.is_relative_to(workspace.resolve()) or not destination.resolve().is_relative_to(managed):
        raise ValidationError("主题目标超出软件管理目录")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.is_symlink() or destination.is_junction():
        raise ValidationError("主题目标不能是链接")
    backup = None
    if destination.exists():
        batch = workspace / "backups/themes" / (datetime.now().strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:8])
        batch.mkdir(parents=True)
        save_json(batch / "recovery.json", {"original_path": str(destination), "kind": "theme"})
        backup = batch / destination.name
        destination.replace(backup)
    try:
        source.replace(destination)
    except OSError:
        if backup is not None:
            backup.replace(destination)
        raise


def apply_files(intent, source, target):
    plan = ConversionPlanner().plan(intent, source_root=source, target_root=target,
                                    source_format="theme", target_format="theme", options=ExportOptions(conflict="overwrite"))
    plan.operations = [op for op in plan.operations if not isinstance(op, WriteManifest)]
    PlanExecutor().execute(plan)


def import_original(workspace, source, cancelled=lambda: False, progress=lambda *_: None, identity=None, remote_directory=""):
    source = Path(source).resolve()
    name = capabilities_name(source)
    if name.endswith("_天马G"):
        raise ValidationError("请选择原版主题，不能将适配结果作为原版。")
    identity = identity or theme_identity(source.name)
    platform_component(identity)
    job = new_job(workspace, "theme-import")
    target = job / "original"
    intent = ExportIntent()
    for relative in source_index(source):
        checkpoint(cancelled)
        intent.files.append(FileRequest(source=source / relative, destination=PurePosixPath(relative), category="media"))
    progress("导入原版：" + name, 30, True)
    apply_files(intent, source, target)
    save_json(target / ".frontendtrans-original.json", {"imported": datetime.now().isoformat(), "source": str(source), "remote_directory": remote_directory})
    promote(target, workspace / "themes/original" / identity, workspace)
    return identity


def sync_originals(workspace, definitions, identities, device, cancelled, progress):
    if device is None:
        raise ValidationError("请先连接设备。")
    available = {info.id: info for info in refresh_themes(workspace, definitions, device, cancelled, progress)}
    for identity in identities:
        info = available.get(identity)
        if info is None or not info.remote_path:
            raise ValidationError("设备上没有可同步的唯一原版主题：" + identity)
        checkpoint(cancelled)
        job = new_job(workspace, "theme-sync")
        target = job / "original"
        progress("同步原版：" + info.name, 20, False)
        subprocess.run([str(device.adb), "-s", device.serial, "pull", info.remote_path, str(target)],
                       capture_output=True, check=True, timeout=3600,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if capabilities_name(target) != info.name:
            raise ValidationError("同步的主题描述与设备列表不一致：" + info.name)
        import_original(workspace, target, cancelled, progress, identity, PurePosixPath(info.remote_path).name)


def adapt_theme(workspace, definitions, info, cancelled, progress):
    from PIL import Image
    from .badges import draw_badge
    if info.source is None:
        raise ValidationError("请先同步或导入原版：" + info.name)
    source = info.source.resolve()
    before_index = source_index(source)
    job = new_job(workspace, "theme-convert")
    destination, generated = job / "complete", job / "generated"
    generated.mkdir()
    parser = ThemeParser(source, cancelled)
    intent = ExportIntent(files=[FileRequest(source=path, destination=PurePosixPath(relative), category="media")
                                for relative, path in parser.files.items() if path.name not in IGNORED])
    progress("复制完整原版：" + info.name, 5, True)
    apply_files(intent, source, destination)
    badge = json_file(Path(__file__).with_name("policies") / "badge.json", {})
    report = {"parser": PARSER_VERSION, "policy": POLICY_VERSION, "platforms": [], "errors": [], "warnings": []}
    configured = bindings(definitions)
    planned = {}
    overlay = ExportIntent()
    for index, binding in enumerate(configured):
        checkpoint(cancelled)
        analysis = parser.analyze(binding.mother, binding.target, binding.name, binding.source_name, binding.id, binding.source_fullname)
        report["platforms"].append({"id": binding.id, "edges": analysis.edges})
        report["errors"].extend(f"{binding.name}: {error}" for error in analysis.errors)
        report["warnings"].extend(f"{binding.name}: {warning}" for warning in analysis.warnings)
        for resource in analysis.resources.values():
            path, relative = resource.source, resource.destination
            if str(relative) in planned:
                if planned[str(relative)] != (str(path), binding.badge):
                    report["errors"].append("平台生成路径冲突：" + str(relative))
                continue
            planned[str(relative)] = (str(path), binding.badge)
            if binding.badge and resource.role == "art" and path.suffix.lower() in {".png", ".webp", ".jpg", ".jpeg"}:
                with Image.open(path) as image:
                    if not getattr(image, "is_animated", False):
                        params = dict(badge["default"])
                        params.update(next(c for c in badge["candidates"] if c["name"] == badge["active_candidate"]))
                        params["text"] = binding.badge
                        output = draw_badge(image, params, badge)
                        asset = generated / (uuid.uuid4().hex + path.suffix)
                        output.convert("RGB" if path.suffix.lower() in {".jpg", ".jpeg"} else "RGBA").save(asset, quality=92)
                        path = asset
            overlay.files.append(FileRequest(source=path, destination=relative, category="media"))
        for relative, xml in analysis.documents.items():
            overlay.texts.append(TextRequest(destination=PurePosixPath(relative), content=xml))
        progress("解析与适配：" + binding.name, 10 + int(75 * (index + 1) / max(1, len(configured))), True)
    save_json(job / "analysis.json", report)
    if report["errors"]:
        raise ValidationError("主题未完整适配：" + "；".join(report["errors"][:8]) + "\n详细报告：" + str(job / "analysis.json"))
    apply_files(overlay, job, destination)
    # Preserve the established Android box/cart proportions from Switch metadata.
    for android in destination.rglob("androidgames.xml"):
        switch = android.with_name("switch.xml")
        if not switch.is_file():
            continue
        current, reference = parse_xml(android.read_bytes(), "theme"), parse_xml(switch.read_bytes(), "theme")
        for tag in ("systemCoverSize", "systemCartSize"):
            replacements = reference.findall(".//" + tag)
            if replacements:
                for node in current.findall(".//" + tag):
                    node.text = replacements[0].text
        android.write_bytes(etree.tostring(current, encoding="utf-8", xml_declaration=True))
    name = capabilities_name(source) + "_天马G"
    platform_component(name)
    previous_records = json_file(workspace / "config/theme-results.json", {})
    if any(key != info.id and value.get("directory") == name for key, value in previous_records.items()):
        raise ValidationError("另一份原版已占用同名输出，请先区分主题名称：" + name)
    capabilities = parse_xml((destination / "capabilities.xml").read_bytes(), "themeCapabilities")
    node = capabilities.find("themeName")
    if node is None:
        node = etree.SubElement(capabilities, "themeName")
    node.text = name
    apply_files(ExportIntent(texts=[TextRequest(destination=PurePosixPath("capabilities.xml"), content=etree.tostring(capabilities, encoding="unicode"))]), source, destination)
    digest, index = fingerprint(source, workspace / "config/theme-cache" / (info.id + ".json"), cancelled)
    if index != before_index:
        raise ValidationError("转换期间原版主题发生变化，请重试；旧结果已保留。")
    checkpoint(cancelled)
    progress("保存完整主题：" + name, 95, False)
    promote(destination, workspace / "themes/exported" / name, workspace)
    records_path = workspace / "config/theme-results.json"
    records = json_file(records_path, {})
    records[info.id] = {"directory": name, "complete": True, "parser": PARSER_VERSION, "policy": POLICY_VERSION,
                        "dependencies": dependencies(definitions), "source_digest": digest, "source_index": index,
                        "output_index": source_index(workspace / "themes/exported" / name),
                        "generated": datetime.now().isoformat(), "report": str(job / "analysis.json")}
    save_json(records_path, records)


def run_themes(operation, workspace, definitions, identities, device, cancelled, progress):
    if operation == "refresh":
        return refresh_themes(workspace, definitions, device, cancelled, progress)
    if operation in {"sync", "sync-convert"}:
        sync_originals(workspace, definitions, identities, device, cancelled, progress)
        if operation == "sync":
            return {"themes": refresh_themes(workspace, definitions, device, cancelled, progress), "message": "原版同步完成。"}
    infos = {info.id: info for info in local_themes(workspace, definitions)}
    if operation in {"convert", "sync-convert"}:
        for identity in identities:
            checkpoint(cancelled)
            try:
                adapt_theme(workspace, definitions, infos[identity], cancelled, progress)
            except ValidationError as exc:
                path = workspace / "config/theme-results.json"
                records = json_file(path, {})
                records.setdefault(identity, {})["last_error"] = str(exc)
                save_json(path, records)
                raise
        return {"themes": local_themes(workspace, definitions), "message": "主题转换完成。"}
    if operation != "upload" or device is None:
        raise ValidationError("请先连接设备。")
    for index, identity in enumerate(identities):
        checkpoint(cancelled)
        info = infos[identity]
        if not info.converted or info.output is None:
            raise ValidationError("转换结果缺失或需要重新转换：" + info.name)
        digest, _ = fingerprint(info.source, workspace / "config/theme-cache" / (info.id + ".json"), cancelled, verify=True)
        record = json_file(workspace / "config/theme-results.json", {}).get(info.id, {})
        if digest != record.get("source_digest"):
            raise ValidationError("原版主题内容已改变，请重新转换：" + info.name)
        progress("上传完整主题：" + info.name, int(index * 100 / len(identities)), False)
        AdbUploader(device.adb, device.serial).upload(info.output, str(PurePosixPath(device.esde_root) / "themes" / info.output_name))
    return {"themes": refresh_themes(workspace, definitions, device, cancelled, progress), "message": "主题上传完成，设备状态已刷新。"}
