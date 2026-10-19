"""Pegasus import conventions observed in SaveDeck library editor 1.0.1."""

import re

from retrolibx.errors import ParseError


ALIASES = {
    "file": "files", "command": "launch", "cwd": "workdir",
    "sort_title": "sort-by", "sort_name": "sort-by", "extensions": "extension",
    "directories": "directory", "ignore-extensions": "ignore-extension",
    "ignore-file": "ignore-files", "developers": "developer", "publishers": "publisher",
    "genres": "genre", "tags": "tag", "assets.boxfront": "assets.box_front",
    "assets.boxart2d": "assets.box_front", "assets.cover": "assets.box_front",
}
LIST_FIELDS = {"files", "extension", "directory", "ignore-extension", "ignore-files",
               "developer", "publisher", "genre", "tag"}


def canonical_fields(record: dict[str, list[str]]) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for key, values in record.items():
        canonical = ALIASES.get(key, key)
        result.setdefault(canonical, []).extend(values)
    for key, values in result.items():
        if key in LIST_FIELDS or key.startswith("assets."):
            continue
        nonempty = list(dict.fromkeys(value.strip() for value in values if value.strip()))
        if len(nonempty) > 1:
            raise ParseError("天马同一字段的值冲突：" + key)
    return result


def value(record: dict[str, list[str]], key: str) -> str:
    values = [part.strip() for part in record.get(key, []) if part.strip()]
    if key in LIST_FIELDS or key.startswith("assets."):
        return "\n".join(values)
    return values[0] if values else ""


def plain_text(text: str) -> str:
    return text.replace("&#x20;", " ").replace("\\_", " ").replace("\\n", "\n")


def command(text: str) -> str:
    return re.sub(r"[\t\r\n ]+", " ", text).strip()


def extensions(record: dict[str, list[str]], consumed: set[str]) -> dict[str, str]:
    result = {}
    for key in sorted(record):
        if key in consumed:
            continue
        text = value(record, key)
        if not text:
            continue
        name = "x_pegasus_" + re.sub(r"[^a-zA-Z0-9]", "_", key)
        if name in result:
            name += "__" + key.encode("utf-8").hex()
        result[name] = text
    return result
