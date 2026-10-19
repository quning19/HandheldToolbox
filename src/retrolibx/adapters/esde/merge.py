"""Preserve user metadata while adding ES-DE records by ROM-relative path."""

import hashlib
from copy import deepcopy
from pathlib import Path, PurePosixPath, PureWindowsPath

from lxml import etree

from retrolibx.core.operations import ExportIntent
from retrolibx.errors import ValidationError
from retrolibx.core.entries import user_state_field


def parse_xml(raw: bytes, expected_root: str) -> etree._Element:
    if b"<!doctype" in raw.lower():
        raise ValidationError("DTD is not supported in configuration XML")
    parser = etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False)
    try:
        root = etree.fromstring(raw, parser)
    except etree.XMLSyntaxError as exc:
        raise ValidationError(f"Invalid {expected_root} XML: {exc}") from exc
    if root.tag != expected_root:
        raise ValidationError(f"Expected {expected_root}, got {root.tag}")
    return root


def xml_text(root: etree._Element) -> str:
    return bytes(
        etree.tostring(root, encoding="UTF-8", xml_declaration=True, pretty_print=True)
    ).decode("utf-8")


def relative_game_path(value: str, rom_root: str, root_aliases: list[str] | None = None) -> str:
    path = PurePosixPath(value.replace("\\", "/"))
    if not value or ".." in path.parts or any(c in value for c in "\r\n\t\x00"):
        raise ValidationError(f"Invalid existing ROM path: {value!r}")
    if PureWindowsPath(rom_root).is_absolute() and PureWindowsPath(value).is_absolute():
        try:
            path = PurePosixPath(
                PureWindowsPath(value).relative_to(PureWindowsPath(rom_root)).as_posix()
            )
        except ValueError as exc:
            raise ValidationError(f"Existing ROM outside system root: {value}") from exc
    elif path.is_absolute():
        for root in [rom_root, *(root_aliases or [])]:
            try:
                path = path.relative_to(PurePosixPath(root))
                break
            except ValueError:
                continue
        else:
            raise ValidationError(f"Existing ROM outside system root: {value}")
    if ":" in path.as_posix() or str(path) == ".":
        raise ValidationError(f"Unsupported ROM path: {value}")
    return "./" + path.as_posix()


def merge_gamelist(generated: str, existing: bytes | None, rom_root: str, root_aliases: list[str] | None = None,
                   *, replace: bool = False, valid_paths: set[str] | None = None,
                   skip_existing: bool = False) -> str:
    incoming = parse_xml(generated.encode("utf-8"), "gameList")
    root = parse_xml(existing, "gameList") if existing is not None else etree.Element("gameList")
    valid = {path.casefold() for path in valid_paths} if valid_paths is not None else None
    records: dict[str, etree._Element] = {}
    for game in root.findall("game"):
        old_path = game.findtext("path") or ""
        relative = relative_game_path(old_path, rom_root, root_aliases)
        key = relative.casefold()
        if root_aliases and PurePosixPath(old_path.replace("\\", "/")).is_absolute():
            game.find("path").text = relative
        if key in records:
            raise ValidationError(f"Duplicate existing ROM path: {key}")
        if valid is not None and key not in valid:
            root.remove(game)
            continue
        records[key] = game
    seen: set[str] = set()
    for game in incoming.findall("game"):
        key = relative_game_path(game.findtext("path") or "", rom_root).casefold()
        if key in seen:
            raise ValidationError(f"Duplicate generated ROM path: {key}")
        seen.add(key)
        if key not in records:
            root.append(deepcopy(game))
            continue
        old = records[key]
        if skip_existing:
            continue
        if replace:
            managed = {"path", "name", "sortname", "desc", "image", "thumbnail", "marquee", "video",
                       "manual", "developer", "publisher", "genre", "releasedate", "players", "rating",
                       "altemulator", "launch"}
            for child in list(old):
                if child.tag in managed and not user_state_field(child.tag):
                    old.remove(child)
        for field in game:
            existing_field = old.find(field.tag)
            if user_state_field(field.tag) and existing_field is not None:
                continue
            if existing_field is None:
                old.append(deepcopy(field))
            elif not (existing_field.text or "").strip():
                existing_field.text = field.text
    return xml_text(root)


def merge_gamelists(
    intent: ExportIntent, snapshot: Path, rom_roots: dict[str, str],
    root_aliases: dict[str, list[str]] | None = None,
    source_systems: dict[str, str] | None = None,
    *, replace: bool = False, valid_paths: dict[str, set[str]] | None = None,
    skip_existing: bool = False,
) -> None:
    """Prepare guarded, preserving gamelist writes for both local and Android exports."""
    root = snapshot.resolve()
    for request in intent.texts:
        parts = request.destination.parts
        if len(parts) != 3 or parts[0] != "gamelists" or parts[2] != "gamelist.xml":
            continue
        old_path = root.joinpath(*parts)
        if not old_path.resolve().is_relative_to(root):
            raise ValidationError(f"Gamelist snapshot path escapes target: {request.destination}")
        if old_path.exists() and not old_path.is_file():
            raise ValidationError(f"Gamelist target is not a file: {old_path}")
        baseline = old_path.read_bytes() if old_path.is_file() else None
        merge_source = baseline
        source_system = (source_systems or {}).get(parts[1])
        if merge_source is None and source_system:
            donor = root / "gamelists" / source_system / "gamelist.xml"
            if not donor.resolve().is_relative_to(root):
                raise ValidationError("Legacy gamelist snapshot escaped its root")
            if donor.is_file():
                merge_source = donor.read_bytes()
        request.content = merge_gamelist(request.content, merge_source, rom_roots[parts[1]], (root_aliases or {}).get(parts[1]),
                                         replace=replace, valid_paths=(valid_paths or {}).get(parts[1]),
                                         skip_existing=skip_existing)
        request.expected_sha256 = (
            hashlib.sha256(baseline).hexdigest() if baseline is not None else ""
        )
        request.backup = True
