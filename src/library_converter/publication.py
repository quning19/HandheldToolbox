"""Publish small task payloads through ordinary ADB after device media I/O."""

import base64
import hashlib
import json
import re
import shlex
import tempfile
import uuid
from pathlib import Path, PurePosixPath

from retrolibx.core.android import android_path
from retrolibx.errors import ValidationError

from frontend_devices.adb import AdbUploader


def _sha(value: str, *, allow_empty: bool = False) -> str:
    if (allow_empty and value == "") or re.fullmatch(r"[0-9a-f]{64}", value):
        return value
    raise ValidationError("Invalid publication SHA-256")


def _inside(value: str, root: PurePosixPath) -> PurePosixPath:
    path = android_path(value)
    if not path.is_relative_to(root) or path == root:
        raise ValidationError(f"Publication path outside its root: {value}")
    return path


def load_publication(task: Path, skip_platform_config: bool = False) -> tuple[dict, dict[str, bytes]]:
    root = task.resolve()
    try:
        data = json.loads((root / "publication.json").read_text(encoding="utf-8"))
        if data["version"] != 1:
            raise ValidationError("Unsupported publication version; rebuild the task")
        source, target, media = (android_path(data[key]) for key in ("source_root", "target_root", "media_root"))
        if source.is_relative_to(target) or target.is_relative_to(source) or source.is_relative_to(media) or media.is_relative_to(source):
            raise ValidationError("Publication source and target overlap")
        payloads = {}
        writes = []
        destinations = set()
        for write in data["writes"]:
            category = write["category"]
            if category == "platform-config" and skip_platform_config:
                continue
            if category == "source-metadata":
                destination = _inside(write["destination"], source)
                if destination.name != "metadata.pegasus.txt" or write["encoding"] != "base64":
                    raise ValidationError("Invalid source metadata publication")
            else:
                destination = _inside(write["destination"], target)
                relative = destination.relative_to(target).parts
                valid = (category == "gamelist" and len(relative) == 3 and relative[0] == "gamelists" and relative[-1] == "gamelist.xml") or (
                    category == "platform-config" and len(relative) == 2 and relative[0] == "custom_systems" and relative[-1] in {
                        "es_systems.xml", "es_find_rules.xml", "es_import_rules.xml", "es_systems_sorting.xml"})
                if not valid or write["encoding"] != "utf-8":
                    raise ValidationError("Invalid XML publication destination")
            if str(destination) in destinations:
                raise ValidationError("Duplicate publication destination")
            destinations.add(str(destination))
            expected = _sha(write["expected_sha256"], allow_empty=True)
            desired = _sha(write["sha256"])
            backup = str(destination) + (".frontendtrans." + expected + ".bak" if category == "source-metadata" else ".frontendtrans.bak")
            versioned = str(destination) + ".frontendtrans." + expected + ".bak"
            if write["backup"] is not None and write["backup"] not in {backup, versioned}:
                raise ValidationError("Invalid publication backup path")
            relative_payload = PurePosixPath(write["payload"])
            if relative_payload.is_absolute() or ".." in relative_payload.parts or not relative_payload.parts or relative_payload.parts[0] != "files":
                raise ValidationError("Invalid local publication payload path")
            payload = root.joinpath(*relative_payload.parts).resolve()
            if not payload.is_relative_to(root):
                raise ValidationError("Publication payload escaped the local task")
            raw = payload.read_bytes()
            if category == "source-metadata":
                raw = base64.b64decode(raw, validate=False)
            if hashlib.sha256(raw).hexdigest() != desired:
                raise ValidationError(f"Publication payload changed: {payload}")
            payloads[str(destination)] = raw
            writes.append(write)
        data["writes"] = writes
        for path, digest in data["guards"].items():
            relative = _inside(path, target).relative_to(target).as_posix()
            if relative not in {"settings/es_settings.xml", "es_settings.xml"}:
                raise ValidationError("Unsupported settings guard")
            _sha(digest)
        for path in data["roms"]:
            _inside(path, source)
        sources = {}
        media_destinations = set()
        for item in data["media"]:
            source_path = android_path(item["source"])
            _inside(item["source"], source if source_path.is_relative_to(source) else media)
            _inside(item["destination"], media)
            if item["destination"] in media_destinations or not isinstance(item["bytes"], int) or item["bytes"] < 0:
                raise ValidationError("Invalid media publication requirement")
            media_destinations.add(item["destination"])
            if item["receipt_key"] is not None:
                _sha(item["receipt_key"])
            if item.get("expected_sha256") is not None:
                _sha(item["expected_sha256"])
            sources[item["source"]] = item["receipt_key"]
        for cleanup in data["cleanup"]:
            _inside(cleanup["source"], source)
            _sha(cleanup["receipt_key"])
            if sources.get(cleanup["source"]) != cleanup["receipt_key"] or not any(w["category"] == "source-metadata" for w in writes):
                raise ValidationError("Source cleanup has no verified media/metadata publication")
            if cleanup["expected_sha256"] is not None:
                _sha(cleanup["expected_sha256"])
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise ValidationError(f"Invalid publication task: {exc}") from exc
    return data, payloads


def plan_publication(task: Path, skip_platform_config: bool = False) -> dict:
    data, payloads = load_publication(task, skip_platform_config)
    return _publication_plan(task, data, payloads, skip_platform_config)


def _publication_plan(task: Path, data: dict, payloads: dict[str, bytes], skip_platform_config: bool) -> dict:
    return {
        "task": str(task.resolve()), "applied": False, "method": "ADB C4",
        "skip_platform_config": skip_platform_config, "required_media": len(data["media"]),
        "writes": [{**write, "bytes": len(payloads[write["destination"]])}
                   for write in data["writes"] if write["sha256"] != write["expected_sha256"]],
        "source_cleanup": data["cleanup"], "device_script_executes": False,
    }


class AdbPublisher(AdbUploader):
    """Guard, back up, push small files via C4, then publish and optional cleanup."""

    def copy_media(self, copies: list[tuple[str, str]], *, overwrite: bool = True) -> None:
        """Copy only selected device media; no ROM transfer or content inspection."""
        pairs = [(android_path(source), android_path(target)) for source, target in copies if source != target]
        # Bound encoded exec-out commands on Windows, including Chinese paths.
        for offset in range(0, len(pairs), 8):
            batch = pairs[offset:offset + 8]
            paths = {path for pair in batch for value in pair for path in (value, *value.parents)}
            commands = [f"test ! -L {shlex.quote(str(path))}" for path in sorted(paths, key=str)]
            for source, target in batch:
                commands.extend((f"mkdir -p -- {shlex.quote(str(target.parent))}",
                                 f"if [ -e {shlex.quote(str(target))} ]; then test -f {shlex.quote(str(target))}; fi",
                                 f"cp {'-f' if overwrite else '-n'} -- {shlex.quote(str(source))} {shlex.quote(str(target))}"))
            if commands:
                self.read("\n".join(commands))

    def publish_config(self, source: Path, destination: str, expected_sha256: str) -> None:
        """Publish one small config via C4 with a baseline and versioned backup."""
        target = android_path(destination)
        expected = _sha(expected_sha256, allow_empty=True)
        desired = hashlib.sha256(source.read_bytes()).hexdigest()
        current = self._digest(str(target))
        if current != expected:
            raise ValidationError(f"设备配置已变化，请重新加载：{target}")
        if current == desired:
            return
        q = shlex.quote
        temporary = str(target) + "." + uuid.uuid4().hex + ".tmp"
        if current:
            backup = str(target) + ".handheldtoolbox." + current + ".bak"
            existing = self._digest(backup)
            if existing not in {"", current}:
                raise ValidationError(f"配置备份冲突：{backup}")
            if not existing:
                self.read(f"cp -- {q(str(target))} {q(backup)}")
                if self._digest(backup) != current:
                    raise ValidationError(f"配置备份未完成：{backup}")
        try:
            self.upload(source, temporary)
            if self._digest(temporary) != desired:
                raise ValidationError(f"设备配置上传不完整，未覆盖：{target}")
            if self._digest(str(target)) != expected:
                raise ValidationError(f"设备配置已变化，未覆盖：{target}")
            self.read(f"mv -f -- {q(temporary)} {q(str(target))}")
        except Exception:
            try:
                self.read(f"rm -f -- {q(temporary)}")
            except ValidationError:
                pass
            raise

    def _safe_paths(self, paths: list[str]) -> None:
        checks = []
        for value in sorted(set(paths)):
            path = android_path(value)
            checks.extend(f"test ! -L {shlex.quote(str(parent))}" for parent in (path, *path.parents))
        if checks:
            self.read("\n".join(checks))

    def _digest(self, path: str) -> str:
        self._safe_paths([path])
        quoted = shlex.quote(path)
        raw = self.read(f"if [ -e {quoted} ]; then test -f {quoted}; sha256sum {quoted}; fi")
        return _sha(raw.decode("utf-8").split(maxsplit=1)[0]) if raw else ""

    def _baseline(self, write: dict) -> str:
        current = self._digest(write["destination"])
        if current not in {write["expected_sha256"], write["sha256"]}:
            raise ValidationError(f"Device file changed; capture/build again: {write['destination']}")
        return current

    def _media(self, data: dict, task: Path) -> dict[str, str]:
        # Ordinary copy has no repeated ROM/media/size checks. Only shared migration,
        # which changes source metadata and can remove originals, requires hashes.
        items = [item for item in data["media"] if item["receipt_key"] is not None]
        if not items:
            return {}
        receipt_file = task.resolve() / "shared-media-hashes.json"
        try:
            receipts = json.loads(receipt_file.read_text(encoding="utf-8")) if receipt_file.exists() else {}
            if not isinstance(receipts, dict):
                raise ValueError("Expected a hash mapping")
            for key, digest in receipts.items():
                _sha(key)
                _sha(digest)
        except (OSError, ValueError, TypeError) as exc:
            raise ValidationError(f"Invalid local shared-media receipt: {exc}") from exc
        for item in items:
            key = item["receipt_key"]
            source_digest = self._digest(item["source"])
            expected = item.get("expected_sha256") or receipts.get(key)
            if source_digest:
                if expected and source_digest != expected:
                    raise ValidationError(f"Shared source changed: {item['source']}")
                receipts[key] = source_digest
            elif expected:
                receipts[key] = expected
            else:
                raise ValidationError(f"Missing shared source and prior receipt: {item['source']}")
            if self._digest(item["destination"]) != receipts[key]:
                raise ValidationError(f"Shared target differs from source receipt: {item['destination']}")
            receipt_file.write_text(json.dumps(receipts, indent=2), encoding="utf-8")
        return receipts

    def publish(self, task: Path, skip_platform_config: bool = False) -> dict:
        data, payloads = load_publication(task, skip_platform_config)
        result = _publication_plan(task, data, payloads, skip_platform_config)
        # Metadata baselines protect existing user fields. Extra media/setting checks
        # are restricted to shared migration before source metadata changes/deletion.
        if any(item["receipt_key"] is not None for item in data["media"]):
            for path, expected in data["guards"].items():
                if self._digest(path) != expected:
                    raise ValidationError(f"ES-DE settings changed; capture/build again: {path}")
        receipts = self._media(data, task)
        for write in data["writes"]:
            self._baseline(write)
            if write["backup"]:
                existing = self._digest(write["backup"])
                if existing and existing != write["expected_sha256"]:
                    raise ValidationError(f"Backup belongs to another baseline: {write['backup']}")
        for cleanup in data["cleanup"]:
            digest = self._digest(cleanup["source"])
            expected = receipts[cleanup["receipt_key"]]
            if (digest and digest != expected) or cleanup["expected_sha256"] not in {None, expected}:
                raise ValidationError(f"Shared source changed: {cleanup['source']}")
        published = []
        with tempfile.TemporaryDirectory(prefix="retrolibx-publish-", dir=getattr(self, "temporary_root", None)) as temporary:
            for number, write in enumerate(data["writes"]):
                current = self._baseline(write)
                if current == write["sha256"]:
                    continue
                destination, backup = write["destination"], write["backup"]
                if current and backup and not self._digest(backup):
                    self.read("cp -- " + shlex.quote(destination) + " " + shlex.quote(backup))
                    if self._digest(backup) != current:
                        raise ValidationError(f"Incomplete backup: {backup}")
                local = Path(temporary) / str(number)
                local.write_bytes(payloads[destination])
                staging = destination + ".frontendtrans." + write["sha256"][:12] + ".tmp"
                self.upload(local, staging)
                if self._digest(staging) != write["sha256"]:
                    raise ValidationError(f"ADB payload differs: {staging}")
                if self._baseline(write) != current:
                    raise ValidationError(f"Destination changed during upload: {destination}")
                self.read("mv -- " + shlex.quote(staging) + " " + shlex.quote(destination))
                if self._digest(destination) != write["sha256"]:
                    raise ValidationError(f"Publication differs: {destination}")
                published.append(destination)
        removed = []
        if data["cleanup"]:
            # All metadata and all shared targets must still match before any source removal.
            for write in data["writes"]:
                if self._digest(write["destination"]) != write["sha256"]:
                    raise ValidationError("Published metadata changed; retain source media")
            receipts = self._media(data, task)
            for cleanup in data["cleanup"]:
                path = cleanup["source"]
                current = self._digest(path)
                if not current:
                    continue
                if current != receipts[cleanup["receipt_key"]]:
                    raise ValidationError(f"Source changed; retain it: {path}")
                self.read("rm -f -- " + shlex.quote(path))
                if self._digest(path):
                    raise ValidationError(f"Source removal failed: {path}")
                removed.append(path)
        return {**result, "applied": True, "serial": self.serial, "published": published, "removed": removed}
