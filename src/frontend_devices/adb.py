"""Batch Android capture and explicit C2/C4 uploads of selected local inputs."""

import base64
import io
import hashlib
import json
import os
import shlex
import subprocess
import tarfile
import tempfile
import uuid
import re
from pathlib import Path, PurePosixPath

from retrolibx.core.android import android_path
from retrolibx.core.entries import DISC_EXTENSIONS
from retrolibx.core.executor import PlanExecutor
from retrolibx.core.operations import ExportIntent, FileRequest, TextRequest
from retrolibx.core.options import ExportOptions
from retrolibx.core.planner import ConversionPlanner
from retrolibx.errors import ValidationError
from retrolibx.adapters.esde.merge import parse_xml
from retrolibx.adapters.pegasus.metadata import parse_metadata
from retrolibx.adapters.pegasus.media import canonical_role
from retrolibx.utils.encoding import detect_metadata_encoding


class AdbReader:
    def __init__(self, adb: Path, serial: str, *, temporary_root: Path | None = None) -> None:
        self.adb, self.serial = adb, serial
        self.temporary_root = temporary_root

    def read(self, command: str, *, timeout: int = 60) -> bytes:
        try:
            devices = subprocess.run(
                [str(self.adb), "devices", "-l"], capture_output=True, check=True, timeout=20,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            ).stdout.decode("utf-8")
            authorized = [
                line.split()[0]
                for line in devices.splitlines()
                if len(line.split()) > 1 and line.split()[1] == "device"
            ]
            if self.serial not in authorized:
                raise ValidationError(f"ADB device not authorized: {self.serial}")
            encoded = base64.b64encode(("set -e\n" + command).encode("utf-8")).decode("ascii")
            marker = "RETROLIBX_STATUS_" + uuid.uuid4().hex + "="
            # Avoid Windows/ADB re-quoting of embedded quotes; keep binary stdout raw.
            remote = f"echo {encoded} | base64 -d | sh; printf '\\n{marker}%s' $?"
            completed = subprocess.run(
                [str(self.adb), "-s", self.serial, "exec-out", remote],
                capture_output=True,
                check=True,
                timeout=timeout,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            raw = completed.stdout
            payload, separator, status = raw.rpartition(("\n" + marker).encode("ascii"))
            if not separator or status.strip() != b"0":
                raise ValidationError(
                    f"ADB command failed ({status.decode('ascii', errors='replace')}): "
                    + (completed.stderr or b"").decode("utf-8", errors="replace").strip()
                )
            return payload
        except (OSError, subprocess.SubprocessError) as exc:
            raise ValidationError(f"ADB read failed: {exc}") from exc


def plan_device_upload(source: Path, destination: str) -> dict[str, object]:
    """Describe one complete directory (C2) or one explicit file (C4)."""
    target = android_path(destination)
    if source.is_symlink() or source.is_junction():
        raise ValidationError("ADB upload source must not be a link or junction")
    local = source.absolute()
    try:
        if local.is_file():
            if destination.endswith("/"):
                raise ValidationError("A file upload needs the complete remote filename")
            method, count, size = "C4", 1, local.stat().st_size
        elif local.is_dir():
            method, count, size = "C2", 0, 0

            def unreadable(error: OSError) -> None:
                raise error

            for directory, folders, files in os.walk(local, onerror=unreadable, followlinks=False):
                for name in folders + files:
                    path = Path(directory) / name
                    if path.is_symlink() or path.is_junction():
                        raise ValidationError(f"ADB upload tree contains a link or junction: {path}")
                    if name in files:
                        if not path.is_file():
                            raise ValidationError(f"Unsupported upload source: {path}")
                        count += 1
                        size += path.stat().st_size
        else:
            raise ValidationError(f"ADB upload source does not exist: {source}")
    except OSError as exc:
        raise ValidationError(f"Cannot read ADB upload source: {exc}") from exc
    return {
        "method": method, "source": str(local), "destination": str(target),
        "files": count, "bytes": size, "deletions": 0,
    }


class AdbUploader(AdbReader):
    """Upload an explicitly selected tree/file without inferring its remote name."""

    def upload(self, source: Path, destination: str) -> dict[str, object]:
        plan = plan_device_upload(source, destination)
        target = android_path(destination)
        q = shlex.quote
        checks = [f"test ! -L {q(str(path))}" for path in (target, *target.parents)]
        if plan["method"] == "C2":
            checks.extend([
                f"if [ -e {q(str(target))} ]; then test -d {q(str(target))}; fi",
                f"if [ -d {q(str(target))} ]; then "
                f"links=$(find {q(str(target))} -type l -print); test -z \"$links\"; fi",
                f"mkdir -p -- {q(str(target))}",
            ])
            # Keep '/.' as a string suffix: Path / '.' would normalize it away.
            local_argument = str(source.absolute()) + "/."
            remote_argument = str(target).rstrip("/") + "/"
        else:
            checks.extend([
                f"if [ -e {q(str(target))} ]; then test -f {q(str(target))}; fi",
                f"mkdir -p -- {q(str(target.parent))}",
            ])
            local_argument, remote_argument = str(source.absolute()), str(target)
        # read() checks devices -l before the remote mkdir and reports shell status.
        self.read("\n".join(checks))
        try:
            subprocess.run(
                [str(self.adb), "-s", self.serial, "push", local_argument, remote_argument],
                capture_output=True, check=True, timeout=3600,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise ValidationError(
                f"ADB upload failed; the destination may contain partial files: {exc}"
            ) from exc
        return {**plan, "serial": self.serial, "applied": True}


def _archive_files(raw: bytes) -> dict[str, bytes]:
    result: dict[str, bytes] = {}
    try:
        with tarfile.open(fileobj=io.BytesIO(raw), mode="r:") as archive:
            for member in archive:
                relative = PurePosixPath(member.name)
                if relative.is_absolute() or ".." in relative.parts:
                    raise ValidationError(f"Invalid remote archive path: {member.name}")
                if member.isdir():
                    continue
                if not member.isfile():
                    raise ValidationError(f"Unsupported link: {member.name}")
                handle = archive.extractfile(member)
                if handle is not None:
                    result[relative.as_posix()] = handle.read()
    except tarfile.TarError as exc:
        raise ValidationError(f"Invalid remote archive: {exc}") from exc
    return result


def capture_pegasus_source(reader: AdbReader, source_root: str, output: Path) -> list[str]:
    """Capture source lists and file names for metadata-only frontend exports."""
    source = android_path(source_root)
    if output.exists():
        raise ValidationError("来源捕获目录必须是新目录")
    q = shlex.quote
    names = reader.read(f"find {q(str(source))} -type f -print0").decode("utf-8").split("\0")
    relatives = set()
    case_names = {}
    for name in filter(None, names):
        path = android_path(name).relative_to(source)
        if not path.parts or ":" in str(path) or "\\" in str(path):
            raise ValidationError(f"无效的设备文件路径：{name}")
        key = path.as_posix().casefold()
        if key in case_names and case_names[key] != path.as_posix():
            raise ValidationError(f"电脑捕获目录不能表示仅大小写不同的设备路径：{path}")
        case_names[key] = path.as_posix()
        relatives.add(path.as_posix())
    metadata = sorted(name for name in relatives if PurePosixPath(name).name == "metadata.pegasus.txt")
    if not metadata:
        raise ValidationError("所选目录没有 metadata.pegasus.txt。")
    downloads = metadata + sorted(name for name in relatives
                                  if PurePosixPath(name).name == "savedeck.toml"
                                  or PurePosixPath(name).suffix.casefold() in DISC_EXTENSIONS)
    contents = {}
    for offset in range(0, len(downloads), 48):
        batch = downloads[offset:offset + 48]
        payload = _archive_files(reader.read(f"tar -cf - -C {q(str(source))} " + " ".join(q(name) for name in batch)))
        if set(payload) != set(batch):
            raise ValidationError("来源配置捕获不完整")
        contents.update(payload)
    output.mkdir(parents=True)
    for name in sorted(relatives):
        destination = output.joinpath(*PurePosixPath(name).parts)
        destination.resolve().relative_to(output.resolve())
        destination.parent.mkdir(parents=True, exist_ok=True)
        # Only metadata, TOML and disc descriptors have content; binary ROMs and
        # media remain file-name markers, never downloaded or uploaded.
        destination.write_bytes(contents.get(name, b""))
    return [PurePosixPath(name).parent.as_posix() for name in metadata]


def capture_device(
    reader: AdbReader,
    source_root: str,
    platforms: list[str],
    esde_root: str,
    output: Path,
    systems_template: Path | None = None,
    *, include_disc_descriptors: bool = False, include_shared_media: bool = False,
) -> dict[str, object]:
    source, target = android_path(source_root), android_path(esde_root)
    if not platforms or (output.exists() and any(output.iterdir())):
        raise ValidationError("Capture needs selected platforms and a new output directory")
    selected = [PurePosixPath(value) for value in sorted(set(platforms))]
    if any(
        path.is_absolute() or ".." in path.parts or any(c in str(path) for c in "\n\r\t\x00")
        for path in selected
    ):
        raise ValidationError("Invalid selected platform")
    q = shlex.quote
    directories = " ".join(q(str(source / path)) for path in selected)
    index = reader.read(f"find {directories} -type f -exec stat -c '%s|%n' {{}} +")
    sizes: dict[str, int] = {}
    try:
        for line in index.decode("utf-8").splitlines():
            size, name = line.split("|", 1)
            relative = PurePosixPath(name).relative_to(source)
            if ".." in relative.parts:
                raise ValueError("Path escaped source")
            sizes[relative.as_posix()] = int(size)
    except (ValueError, UnicodeError) as exc:
        raise ValidationError(f"Invalid device index: {exc}") from exc
    metadata = [str(path / "metadata.pegasus.txt") for path in selected]
    if any(name not in sizes for name in metadata):
        raise ValidationError("A selected platform has no metadata.pegasus.txt")
    nested = [
        PurePosixPath(name).parent
        for name in sizes
        if name.endswith("/metadata.pegasus.txt") and name not in metadata
    ]
    sizes = {
        name: size
        for name, size in sizes.items()
        if not any(PurePosixPath(name).is_relative_to(path) for path in nested)
    }
    download_names = list(metadata)
    if include_disc_descriptors:
        download_names.extend(name for name in sizes if PurePosixPath(name).suffix.casefold() in {".cue", ".gdi", ".m3u", ".ccd"})
    contents = _archive_files(
        reader.read(f"tar -cf - -C {q(str(source))} " + " ".join(q(name) for name in download_names))
    )
    if set(contents) != set(download_names):
        raise ValidationError("Incomplete metadata archive; no capture was written")
    target_exists = reader.read(f"if [ -d {q(str(target))} ]; then printf yes; fi") == b"yes"
    snapshot: dict[str, bytes] = {}
    if target_exists:
        listing = (
            reader.read(
                f"cd {q(str(target))} && find . -type f -name '*.xml' "
                "| grep -E '^./(gamelists/|custom_systems/|settings/es_settings.xml$|es_settings.xml$)' || true"
            )
            .decode("utf-8")
            .splitlines()
        )
        if listing:
            snapshot = _archive_files(
                reader.read(
                    f"tar -cf - -C {q(str(target))} " + " ".join(q(name) for name in listing)
                )
            )
    aliases: dict[str, dict[str, str]] = {}
    shared_sources: dict[str, str] = {}
    if include_shared_media:
        media_root = target / "downloaded_media"
        settings = snapshot.get("settings/es_settings.xml") or snapshot.get("es_settings.xml")
        if settings:
            fragment = re.sub(rb"^\s*(?:\xef\xbb\xbf)?<\?xml[^?]*\?>", b"", settings, count=1)
            try:
                settings_root = parse_xml(settings, "config")
            except ValidationError:
                settings_root = parse_xml(b"<config>" + fragment + b"</config>", "config")
            node = settings_root.find("string[@name='MediaDirectory']")
            if node is not None and node.get("value"):
                media_root = android_path(node.get("value"))
        references: dict[str, list[tuple[str, str]]] = {}
        for name in metadata:
            platform = PurePosixPath(name).parent.as_posix()
            for record in parse_metadata(contents[name].decode(detect_metadata_encoding(contents[name]))):
                for key, values in record.items():
                    if not key.startswith("assets.") or canonical_role(key[7:]) not in {"box_front", "logo", "marquee", "video"}:
                        continue
                    for value in values:
                        path = PurePosixPath(value)
                        if path.is_absolute() and ".." not in path.parts and path.is_relative_to(media_root) and path != media_root:
                            android_path(value)
                            references.setdefault(value, []).append((platform, value))
        paths = list(references)
        for offset in range(0, len(paths), 48):
            arguments = " ".join(q(value) for value in paths[offset:offset + 48])
            raw = reader.read(f"for file in {arguments}; do if [ -f \"$file\" ]; then stat -c '%s|%n' \"$file\"; fi; done")
            for line in raw.decode("utf-8").splitlines():
                size, remote = line.split("|", 1)
                if remote not in references:
                    raise ValidationError("Unexpected shared media index path")
                for platform, reference in references[remote]:
                    virtual = str(PurePosixPath(platform) / ".frontendtrans-index" / (
                        hashlib.sha256(remote.encode("utf-8")).hexdigest() + PurePosixPath(remote).suffix))
                    sizes[virtual] = int(size)
                    aliases.setdefault(platform, {})[reference] = "Roms/" + virtual
                    shared_sources[virtual] = remote
    config: dict[str, object] = {
        "source_root": "Roms",
        "device_rom_root": str(source),
        "esde_root": str(target),
        "systems_template": str(systems_template.resolve()) if systems_template else None,
        "target_empty": not target_exists,
        "target_snapshot": "snapshot" if target_exists else None,
        "device_index": "device-index.json",
        "media_path_aliases": aliases,
        "device_media_sources": shared_sources,
    }
    intent = ExportIntent(
        texts=[
            TextRequest(
                destination=PurePosixPath("device-index.json"),
                content=json.dumps(
                    {"serial": reader.serial, "source_root": str(source), "sizes": sizes},
                    ensure_ascii=False,
                    indent=2,
                ),
            ),
            TextRequest(
                destination=PurePosixPath("config.json"),
                content=json.dumps(config, ensure_ascii=False, indent=2),
            ),
        ]
    )
    with tempfile.TemporaryDirectory(prefix="retrolibx-capture-", dir=getattr(reader, "temporary_root", None)) as temporary:
        staging = Path(temporary)
        for name in sizes:
            if name not in contents:
                intent.texts.append(
                    TextRequest(destination=PurePosixPath("Roms") / name, content="")
                )
        for prefix, files in (("Roms", contents), ("snapshot", snapshot)):
            for number, (file_relative, data) in enumerate(files.items()):
                path = staging / f"{prefix}-{number}"
                path.write_bytes(data)
                intent.files.append(
                    FileRequest(
                        source=path,
                        destination=PurePosixPath(prefix) / file_relative,
                        category="media",
                    )
                )
        if target_exists and not snapshot:
            intent.directories.append(PurePosixPath("snapshot"))
        plan = ConversionPlanner().plan(
            intent,
            source_root=staging,
            target_root=output,
            source_format="android-index",
            target_format="local-catalog",
            options=ExportOptions(),
        )
        PlanExecutor().execute(plan)
    return {
        "serial": reader.serial,
        "indexed_files": len(sizes),
        "downloaded_metadata": len(metadata),
        "downloaded_descriptors": len(contents) - len(metadata),
        "downloaded_config": len(snapshot),
        "media_downloaded": 0,
    }
