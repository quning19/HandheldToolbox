"""Read, render and merge SaveDeck v1 documents without losing user fields."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import PurePosixPath
import tomllib
from uuid import UUID

from retrolibx.errors import ValidationError
from retrolibx.core.entries import user_state_field


def relative_path(value: str) -> PurePosixPath:
    path = PurePosixPath(value)
    if (not value or path.is_absolute() or ".." in path.parts or not path.parts
            or any(c in value for c in "\\:\x00\r\n") or value.startswith("./")):
        raise ValidationError(f"SaveDeck 路径必须为平台内相对路径：{value!r}")
    return path


def validate_document(data: dict) -> dict:
    if type(data.get("format_version", 1)) is not int or data.get("format_version", 1) != 1:
        raise ValidationError("仅支持 SaveDeck format_version = 1")
    if not isinstance(data.get("platform"), str) or not data["platform"].strip():
        raise ValidationError("SaveDeck 缺少平台名称")
    if not isinstance(data.get("games"), list):
        raise ValidationError("SaveDeck 缺少 games 列表")
    files, ids = set(), set()
    for key in ("sort", "launch"):
        if key in data and not isinstance(data[key], str):
            raise ValidationError(f"SaveDeck {key} 必须为字符串")
    for game in data["games"]:
        if not isinstance(game, dict) or not isinstance(game.get("name"), str) or not game["name"].strip():
            raise ValidationError("SaveDeck 游戏缺少名称")
        for key in ("name", "file", "sort", "description", "cover", "video", "launch", "id"):
            if key in game and not isinstance(game[key], str):
                raise ValidationError(f"SaveDeck 游戏字段 {key} 必须为字符串")
        reference = relative_path(game.get("file", "")).as_posix().casefold()
        if reference in files:
            raise ValidationError(f"SaveDeck ROM 路径重复：{game['file']}")
        files.add(reference)
        for key in ("cover", "video"):
            if key in game:
                relative_path(game[key])
        if "id" in game:
            try:
                identifier = str(UUID(game["id"]))
            except ValueError as exc:
                raise ValidationError("SaveDeck 游戏 ID 必须是小写 UUID") from exc
            if identifier != game["id"] or identifier in ids:
                raise ValidationError("SaveDeck 游戏 ID 重复或不是小写 UUID")
            ids.add(identifier)
    return data


def parse_document(raw: bytes) -> dict:
    try:
        return validate_document(tomllib.loads(raw.decode("utf-8-sig")))
    except (UnicodeError, tomllib.TOMLDecodeError) as exc:
        raise ValidationError(f"无法读取 SaveDeck 配置：{exc}") from exc


def _quote(value: str) -> str:
    controls = any(ord(c) < 32 and c not in "\n\t" or ord(c) == 127 for c in value)
    if "'" not in value and not controls:
        if "\n" in value:
            return "'''" + ("\n" if value.startswith("\n") else "") + value + "'''"
        return "'" + value + "'"
    return json.dumps(value, ensure_ascii=False).replace("\x7f", "\\u007f")


def _key(value: str) -> str:
    return value if value and all(c.isascii() and (c.isalnum() or c in "_-") for c in value) else _quote(value)


def _value(value) -> str:
    # Preserve unknown TOML fields when merging a user-maintained document.
    if isinstance(value, str):
        return _quote(value)
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, list):
        return "[" + ", ".join(_value(item) for item in value) + "]"
    if isinstance(value, dict):
        return "{ " + ", ".join(_key(k) + " = " + _value(v) for k, v in value.items()) + " }"
    if hasattr(value, "isoformat"):
        return value.isoformat()
    raise ValidationError(f"不能保留 SaveDeck 字段类型：{type(value).__name__}")


def render_document(data: dict) -> str:
    validate_document(data)
    lines = [""] + [_key(key) + " = " + _value(data[key])
             for key in sorted(data) if key != "games" and not key.startswith("x_pegasus_")]
    extras = [key for key in sorted(data) if key.startswith("x_pegasus_")]
    if extras:
        lines.append("")
        lines.extend(_key(key) + " = " + _value(data[key]) for key in extras)
    if not data["games"]:
        lines.append("games = []")
    if data["games"]:
        lines.append("")
    for game in data["games"]:
        lines.extend(("", "[[games]]"))
        lines.extend(_key(key) + " = " + _value(game[key]) for key in sorted(game))
    return "\n".join(lines) + "\n"


def apply_source_order(data: dict, source_order: list[str]) -> dict:
    """Refresh only entry order and sort numbers after merging user-owned fields."""
    ranks = {relative_path(path).as_posix().casefold(): index for index, path in enumerate(source_order)}
    data["games"].sort(key=lambda game: ranks.get(game["file"].casefold(), len(ranks)))
    for index, game in enumerate(data["games"], 1):
        game["sort"] = f"{index:06d}"
    return data


def merge_documents(existing: dict, incoming: dict, *, replace: bool = False,
                    valid_files: set[str] | None = None) -> dict:
    validate_document(existing)
    validate_document(incoming)
    result = deepcopy(existing)
    if valid_files is not None:
        valid = {relative_path(path).as_posix().casefold() for path in valid_files}
        result["games"] = [game for game in result["games"] if game["file"].casefold() in valid]
    if replace:
        for key in list(result):
            if key != "games" and (key in {"format_version", "platform", "sort", "launch"} or key.startswith("x_pegasus_")):
                if not user_state_field(key):
                    result.pop(key)
    for key, value in incoming.items():
        if key != "games" and (replace or result.get(key) in (None, "")):
            if user_state_field(key) and key in result:
                continue
            result[key] = deepcopy(value)
    by_file = {relative_path(game["file"]).as_posix().casefold(): game for game in result["games"]}
    for game in incoming["games"]:
        identity = relative_path(game["file"]).as_posix().casefold()
        old = by_file.get(identity)
        if old is None:
            added = deepcopy(game)
            if valid_files is not None and not replace:
                last = max((int(entry["sort"]) for entry in result["games"]
                            if isinstance(entry.get("sort"), str) and entry["sort"].isdigit()), default=0)
                added["sort"] = f"{last + 1:06d}"
            result["games"].append(added)
            by_file[identity] = added
        else:
            if valid_files is not None and not replace:
                continue  # Default synchronization leaves surviving entries untouched.
            if replace:
                for key in list(old):
                    if (key in {"name", "file", "sort", "description", "cover", "video", "launch"}
                            or key.startswith("x_pegasus_")) and not user_state_field(key):
                        old.pop(key)
            for key, value in game.items():
                if user_state_field(key) and key in old:
                    continue
                if replace or old.get(key) in (None, ""):
                    old[key] = deepcopy(value)
    return validate_document(result)
