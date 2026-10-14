"""Pegasus metadata stanza parser and writer."""

from __future__ import annotations

import codecs
import re
from collections.abc import Iterable

from retrolibx.errors import ParseError

from .media import canonical_role


def parse_metadata(text: str) -> list[dict[str, list[str]]]:
    records: list[dict[str, list[str]]] = []
    current: dict[str, list[str]] = {}
    last_key: str | None = None
    for number, raw_line in enumerate(text.lstrip("\ufeff").splitlines(), 1):
        if raw_line.lstrip().startswith("#"):
            continue
        if not raw_line.strip():
            continue
        if raw_line[:1].isspace() and last_key:
            value = raw_line.strip()
            if last_key in {"files", "file", "ignore-files", "directories", "extensions"}:
                current[last_key].append(value)
            else:
                current[last_key][-1] += "\n" + value
            continue
        if ":" not in raw_line:
            raise ParseError(f"Invalid Pegasus entry at line {number}")
        key, value = raw_line.split(":", 1)
        last_key = key.strip().casefold()
        if last_key in {"collection", "game"} and current:
            records.append(current)
            current = {}
        current.setdefault(last_key, []).append(value.strip())
    if current:
        records.append(current)
    return records


def field(record: dict[str, list[str]], key: str) -> str | None:
    values = record.get(key)
    return values[-1] if values else None


def render_records(records: Iterable[list[tuple[str, str | None]]]) -> str:
    blocks: list[str] = []
    for record in records:
        lines: list[str] = []
        for key, value in record:
            if value is None or value == "":
                continue
            parts = str(value).splitlines() or [""]
            lines.append(f"{key}: {parts[0]}")
            lines.extend(f"  {part}" for part in parts[1:])
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks) + "\n"


def patch_asset_references(
    raw: bytes, replacements: dict[int, dict[str, str]], encoding: str,
) -> bytes:
    """Change game asset values without re-rendering other metadata bytes."""
    codec = codecs.lookup(encoding).name
    prefix = b""
    for mark, byte_codec in (
        (codecs.BOM_UTF32_LE, "utf-32-le"), (codecs.BOM_UTF32_BE, "utf-32-be"),
        (codecs.BOM_UTF8, "utf-8"),
        (codecs.BOM_UTF16_LE, "utf-16-le"), (codecs.BOM_UTF16_BE, "utf-16-be"),
    ):
        if raw.startswith(mark) and codec.startswith(byte_codec.split("-le")[0].split("-be")[0]):
            prefix, codec = mark, byte_codec
            break
    if codec == "utf-8-sig":
        codec = "utf-8"
    text = raw[len(prefix):].decode(codec)
    if prefix + text.encode(codec) != raw:
        raise ParseError("Metadata encoding cannot be preserved exactly")
    lines = text.splitlines(keepends=True)
    starts = [i for i, line in enumerate(lines) if re.match(r"(?i)^game\s*:", line)]
    if any(index < 0 or index >= len(starts) for index in replacements):
        raise ParseError("Source game record changed before asset patching")
    asset = re.compile(r"(?i)^(assets\.([^:]+)[ \t]*:[ \t]*)([^\r\n]*)(\r\n|\n|\r)?$")
    for game_index in sorted(replacements, reverse=True):
        start = starts[game_index]
        end = starts[game_index + 1] if game_index + 1 < len(starts) else len(lines)
        block = lines[start:end]
        updates = replacements[game_index]
        if any(role not in {"box_front", "logo", "video"} for role in updates):
            raise ParseError("Only cover, logo and video references may be patched")
        if any(any(c in value for c in "\r\n\t\x00") for value in updates.values()):
            raise ParseError("Invalid asset reference")
        present: set[str] = set()
        for index, line in enumerate(block):
            match = asset.match(line)
            if not match:
                continue
            role = canonical_role(match.group(2).strip().casefold())
            if role not in updates:
                continue
            # Do not silently leave an old path continuation attached to a new value.
            if index + 1 < len(block) and block[index + 1][:1].isspace() and block[index + 1].strip():
                if not block[index + 1].lstrip().startswith("#"):
                    raise ParseError("Multiline asset reference requires manual resolution")
            block[index] = match.group(1) + updates[role] + (match.group(4) or "")
            present.add(role)
        missing = [role for role in ("box_front", "logo", "video") if role in updates and role not in present]
        if missing:
            meaningful = [i for i, line in enumerate(block) if line.strip() and not line.lstrip().startswith("#")]
            insert = meaningful[-1] + 1
            ending = next(
                (match.group(0) for line in block if (match := re.search(r"\r\n|\n|\r$", line))),
                "\n",
            )
            if not block[insert - 1].endswith(("\r", "\n")):
                block[insert - 1] += ending
            block[insert:insert] = [f"assets.{role}: {updates[role]}{ending}" for role in missing]
        lines[start:end] = block
    return prefix + "".join(lines).encode(codec)
