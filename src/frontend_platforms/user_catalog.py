"""Default platform catalog plus durable edits; no GUI or converter imports."""
from __future__ import annotations
from dataclasses import asdict, dataclass
import json
from pathlib import Path
from frontend_platforms import PlatformRegistry, platform_component


@dataclass
class PlatformDefinition:
    id: str
    name: str
    directory: str
    parent: str = ""
    mode: str = "inherit"
    badge: str = ""


def default_definitions():
    definitions = [PlatformDefinition(
        r["name"], r.get("theme_label") or r["rom_directory"], r["rom_directory"],
        r.get("base_platform") or "", "separate" if r.get("base_platform") else "inherit",
        r.get("badge_text") or "",
    ) for r in PlatformRegistry.load().records.values()]
    if not any(item.id == "pspminis" for item in definitions):
        definitions.append(PlatformDefinition("pspminis", "PSP Minis", "PSP Minis", "psp"))
    return definitions


def valid_component(value):
    try:
        platform_component(value)
    except (TypeError, ValueError):
        return False
    return True


def validate_definitions(definitions):
    for item in definitions:
        if not all(isinstance(value, str) for value in asdict(item).values()):
            raise ValueError("平台字段必须是文字。")
        if not item.name.strip() or not valid_component(item.id) or not valid_component(item.directory):
            raise ValueError("平台名称、标识或 ROM 目录无效。")
        if item.mode not in {"inherit", "separate"}:
            raise ValueError("平台主题表现无效。")
    by_id = {item.id: item for item in definitions}
    if len(by_id) != len(definitions):
        raise ValueError("平台内部标识重复。")
    directories = [item.directory.casefold() for item in definitions]
    if len(set(directories)) != len(directories):
        raise ValueError("平台 ROM 目录重复。")
    for item in definitions:
        visited = {item.id}
        parent = item.parent
        while parent:
            if parent not in by_id or parent in visited:
                raise ValueError("平台母体引用缺失或存在循环。")
            visited.add(parent)
            parent = by_id[parent].parent


def encode_overrides(definitions, defaults=None, previous=None):
    validate_definitions(definitions)
    baseline = defaults if defaults is not None else default_definitions()
    by_id = {item.id: asdict(item) for item in baseline}
    old = dict((previous or {}).get("defaults", {}))
    old.update(by_id)
    overrides, custom = {}, []
    for item in definitions:
        fields = asdict(item)
        base = by_id.get(item.id)
        if base is None:
            custom.append(fields)
        else:
            delta = {k: v for k, v in fields.items() if k != "id" and base[k] != v}
            if delta:
                overrides[item.id] = delta
    disabled = (set(by_id) | set((previous or {}).get("disabled", []))) - {item.id for item in definitions}
    return {"version": 2, "defaults": old, "overrides": overrides, "custom": custom,
            "disabled": sorted(disabled)}


def merge_catalog(document, defaults=None):
    baseline = defaults if defaults is not None else default_definitions()
    if document.get("version") != 2:
        raise ValueError("平台配置版本无效。")
    current = {item.id: asdict(item) for item in baseline}
    disabled = set(document.get("disabled", []))
    custom = document.get("custom", [])
    notices = []
    rows = {item["id"]: dict(item) for item in custom}
    if len(rows) != len(custom):
        raise ValueError("用户平台标识重复。")
    for identifier, fields in document.get("overrides", {}).items():
        base = current.get(identifier) or document.get("defaults", {}).get(identifier)
        if base is None:
            raise ValueError("找不到用户修改的平台基线：" + identifier)
        rows.setdefault(identifier, {**base, **fields, "id": identifier})
    for identifier, fields in document.get("defaults", {}).items():
        if identifier not in current and identifier not in disabled and identifier not in rows:
            rows[identifier] = dict(fields)
            notices.append("默认平台停止维护，保留现有定义：" + identifier)
    for identifier, fields in current.items():
        if identifier in disabled:
            continue
        if fields.get("parent") in disabled and identifier not in rows:
            notices.append("新版默认平台引用了已禁用母体，未自动加入：" + identifier)
            continue
        if identifier in rows:
            if any(item["id"] == identifier for item in custom):
                notices.append("新版默认标识冲突，保留用户平台：" + identifier)
            continue
        if any(item["directory"].casefold() == fields["directory"].casefold() for item in rows.values()):
            notices.append("新版默认目录冲突，未自动加入：" + identifier)
            continue
        rows[identifier] = fields
    # Preserve retired parent chains; malformed graphs still fail without rewriting input.
    for item in list(rows.values()):
        parent = item.get("parent", "")
        visited = set()
        while parent and parent not in rows and parent not in visited:
            visited.add(parent)
            old = document.get("defaults", {}).get(parent)
            if old is None or parent in disabled:
                break
            rows[parent] = dict(old)
            notices.append("保留停止维护的母体定义：" + parent)
            parent = old.get("parent", "")
    protected = {item["id"] for item in custom} | set(document.get("overrides", {}))
    while True:
        missing = [key for key, row in rows.items() if row.get("parent") and row["parent"] not in rows and key not in protected]
        if not missing:
            break
        for key in missing:
            del rows[key]
            notices.append("母体存在升级冲突，未自动加入默认平台：" + key)
    order = [identifier for identifier in current if identifier in rows]
    order.extend(identifier for identifier in rows if identifier not in current)
    result = [PlatformDefinition(**rows[identifier]) for identifier in order]
    validate_definitions(result)
    return result, notices


def load_catalog(workspace: Path):
    from frontend_common.files import write_json
    path = workspace / "config/platforms.json"
    if not path.is_file():
        return default_definitions(), []
    content = json.loads(path.read_text(encoding="utf-8"))
    if content.get("version") == 1:
        definitions = [PlatformDefinition(**row) for row in content["platforms"]]
        validate_definitions(definitions)
        baseline = Path(__file__).with_name("baseline-v1.json")
        if baseline.is_file():
            old = [PlatformDefinition(**row) for row in json.loads(baseline.read_text(encoding="utf-8"))]
            converted = encode_overrides(definitions, old)
            notices = ["已按旧版默认表迁移，原平台配置保存在 backups/config。"]
        else:
            converted = {"version": 2, "defaults": {}, "custom": [asdict(item) for item in definitions], "overrides": {}, "disabled": []}
            notices = ["旧版基线缺失，保留所有现有字段，未推断用户删除。"]
        result, upgrade = merge_catalog(converted)
        backup = workspace / "backups/config/platforms-v1.json"
        if backup.exists() and backup.read_bytes() != path.read_bytes():
            raise ValueError("已有不同的平台迁移备份，请先另存备份文件。")
        backup.parent.mkdir(parents=True, exist_ok=True)
        backup.write_bytes(path.read_bytes())
        write_json(path, converted)
        return result, notices + upgrade
    return merge_catalog(content)


def save_catalog(workspace, definitions):
    from frontend_common.files import write_json
    path = workspace / "config/platforms.json"
    previous = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    write_json(path, encode_overrides(definitions, previous=previous))
