"""Render a minimal device copy script and separate host publication payloads."""

import base64
import hashlib
import json
import shlex
from pathlib import Path, PurePosixPath

from .operations import ConversionPlan, TransferFile, WriteText, WriteSourceMetadata, MigrateSourceMedia
from retrolibx.errors import ValidationError


def android_path(value: str) -> PurePosixPath:
    path = PurePosixPath(value)
    if (not path.is_absolute() or ".." in path.parts or len(path.parts) < 4
            or any(c in value for c in "\r\n\t\x00")):
        raise ValidationError(f"Invalid Android directory: {value!r}")
    return path


def android_intent_command(command: str) -> str:
    """Translate the explicitly selected am-start form; never run source commands."""
    try:
        tokens = shlex.split(command)
    except ValueError as exc:
        raise ValidationError(f"Invalid metadata launch: {exc}") from exc
    if tokens[:2] != ["am", "start"]:
        raise ValidationError("Metadata launch must use am start")
    component, user, clear_top = None, None, False
    extras: dict[str, str] = {}
    index = 2
    while index < len(tokens):
        token = tokens[index]
        if token == "--activity-clear-top":
            clear_top = True
            index += 1
            continue
        count = 2 if token == "-e" else 1
        if token not in {"-n", "--user", "-e"} or index + count >= len(tokens):
            raise ValidationError(f"Unsupported metadata launch argument: {token}")
        value = tokens[index + 1]
        if token == "-n":
            component = value
        elif token == "--user":
            user = value
        else:
            if value in extras:
                raise ValidationError(f"Duplicate metadata launch extra: {value}")
            extras[value] = tokens[index + 2]
        index += count + 1
    if user != "0" or not component or "/" not in component or extras.get("ROM") != "{file.path}":
        raise ValidationError("Metadata launch needs user 0, an explicit component and ROM {file.path}")
    values = [component, *extras.keys(), *extras.values()]
    if any(any(c.isspace() or c in "%\x00" for c in value) for value in values):
        raise ValidationError("Unsupported whitespace or expansion in metadata launch")
    result = "%ANDROIDAPP%=" + component
    for key, value in extras.items():
        result += " %EXTRA_" + key + "%=" + ("%ROMRAW%" if value == "{file.path}" else value)
    return result + (" %ACTIVITY_CLEAR_TOP%" if clear_top else "")


def render_android_script(
    plan: ConversionPlan,
    source_root: str,
    target_root: str,
    rom_paths: list[Path],
    source_sizes: dict[str, int] | None = None,
    media_root: str | None = None,
    config_checks: dict[str, str] | None = None,
    media_source_overrides: dict[str, str] | None = None,
    versioned_backups: bool = False,
) -> tuple[str, dict[str, str]]:
    source, target = android_path(source_root), android_path(target_root)
    media_target = android_path(media_root) if media_root else target / "downloaded_media"
    if source.is_relative_to(target) or target.is_relative_to(source) or source.is_relative_to(media_target) or media_target.is_relative_to(source):
        raise ValidationError("Android source and target directories overlap")
    sizes = source_sizes or {}
    payload: dict[str, str] = {}
    publication: dict = {
        "version": 1, "source_root": str(source), "target_root": str(target),
        "media_root": str(media_target), "guards": config_checks or {},
        "roms": [str(source / path.relative_to(plan.source_root).as_posix()) for path in rom_paths],
        "media": [], "writes": [], "cleanup": [],
    }
    migrations = {op.destination: op for op in plan.operations if isinstance(op, MigrateSourceMedia)}
    keys = {path: hashlib.sha256(path.relative_to(plan.source_root).as_posix().encode("utf-8")).hexdigest()
            for path in migrations}
    for path, migration in migrations.items():
        if migration.cleanup:
            publication["cleanup"].append({
                "source": str(source / path.relative_to(plan.source_root).as_posix()),
                "receipt_key": keys[path], "expected_sha256": migration.expected_sha256,
            })
    directories = set()
    copies = []
    for operation in plan.operations:
        if isinstance(operation, TransferFile) and operation.category == "media":
            relative = operation.source.relative_to(plan.source_root).as_posix()
            src = (media_source_overrides or {}).get(relative, str(source / relative))
            if src != str(source / relative) and not android_path(src).is_relative_to(media_target):
                raise ValidationError("Indexed shared media source escaped ES-DE MediaDirectory")
            relative_target = operation.destination.relative_to(plan.target_root)
            destination = media_target / PurePosixPath(*relative_target.parts[1:])
            directories.add(str(destination.parent))
            # Full replacement overwrites selected media; normal copies skip existing files.
            flag = "-f" if operation.overwrite or plan.conflict_policy == "overwrite" else "-n"
            if src != str(destination):
                copies.append(f"cp {flag} -- {shlex.quote(src)} {shlex.quote(str(destination))}")
            publication["media"].append({
                "source": src, "destination": str(destination),
                "bytes": sizes.get(relative, operation.source.stat().st_size),
                "receipt_key": keys.get(operation.source),
                "expected_sha256": migrations[operation.source].expected_sha256 if operation.source in migrations else None,
            })
        elif isinstance(operation, WriteText):
            relative = operation.destination.relative_to(plan.target_root).as_posix()
            destination = str(target / relative)
            payload["files/" + relative] = operation.content
            publication["writes"].append({
                "category": "platform-config" if relative.startswith("custom_systems/") else "gamelist",
                "destination": destination, "payload": "files/" + relative, "encoding": "utf-8",
                "expected_sha256": operation.expected_sha256 or "",
                "sha256": hashlib.sha256(operation.content.encode("utf-8")).hexdigest(),
                "backup": destination + (
                    ".frontendtrans." + operation.expected_sha256 + ".bak"
                    if versioned_backups and operation.expected_sha256 else ".frontendtrans.bak"
                ) if operation.backup else None,
            })
        elif isinstance(operation, WriteSourceMetadata):
            relative = operation.destination.relative_to(plan.source_root).as_posix()
            destination = str(source / relative)
            name = "files/source-metadata/" + relative + ".b64"
            payload[name] = operation.content_base64 + "\n"
            publication["writes"].append({
                "category": "source-metadata", "destination": destination, "payload": name,
                "encoding": "base64", "expected_sha256": operation.expected_sha256,
                "sha256": hashlib.sha256(base64.b64decode(operation.content_base64, validate=True)).hexdigest(),
                "backup": destination + ".frontendtrans." + operation.expected_sha256 + ".bak",
            })
    lines = ["#!/system/bin/sh", "set -e"]
    if directories:
        lines.append("mkdir -p -- " + " ".join(shlex.quote(path) for path in sorted(directories)))
    lines.extend(copies)
    payload["publication.json"] = json.dumps(publication, ensure_ascii=False, indent=2) + "\n"
    return "\n".join(lines) + "\n", payload
