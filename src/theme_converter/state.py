"""Content fingerprints and output-relevant platform dependencies."""
from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
from frontend_common.files import write_json
from frontend_common.jobs import checkpoint
from frontend_platforms import PlatformRegistry

IGNORED = {".frontendtrans-original.json", "_build_report.txt", "_verify.txt", "_manifest.json"}


def source_index(source: Path):
    result = {}
    for path in source.rglob("*"):
        if path.is_symlink() or path.is_junction():
            raise ValueError("原版主题中存在链接：" + str(path))
        if path.is_file() and ".git" not in path.relative_to(source).parts and path.name not in IGNORED:
            stat = path.stat()
            result[path.relative_to(source).as_posix()] = [stat.st_size, stat.st_mtime_ns]
    return result


def fingerprint(source, cache_path, cancelled=lambda: False, *, verify=False):
    index = source_index(source)
    try:
        cache = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.is_file() else {}
    except (OSError, ValueError):
        cache = {}  # Derived file hashes can be regenerated without altering user settings.
    hashes = {}
    for relative, stat in sorted(index.items()):
        checkpoint(cancelled)
        old = cache.get("files", {}).get(relative, {})
        if not verify and old.get("stat") == stat:
            digest = old["hash"]
        else:
            hasher = hashlib.sha256()
            with (source / relative).open("rb") as handle:
                for block in iter(lambda: handle.read(1024 * 1024), b""):
                    checkpoint(cancelled)
                    hasher.update(block)
            digest = hasher.hexdigest()
        hashes[relative] = {"stat": stat, "hash": digest}
    digest = hashlib.sha256(json.dumps({k: v["hash"] for k, v in hashes.items()}, sort_keys=True).encode()).hexdigest()
    write_json(cache_path, {"files": hashes, "digest": digest})
    return digest, index


@dataclass
class Binding:
    id: str
    target: str
    mother: str
    source_name: str
    source_fullname: str
    name: str
    badge: str
    dependencies: list


def bindings(definitions):
    registry = PlatformRegistry.load()
    by_id = {item.id: item for item in definitions}
    result = []
    for item in definitions:
        if not item.parent or item.mode == "inherit":
            continue
        chain, current, visited = [], item, set()
        while True:
            if current.id in visited:
                raise ValueError("平台母体循环：" + current.id)
            visited.add(current.id)
            chain.append(asdict(current))
            if not current.parent:
                break
            current = by_id[current.parent]
        target_record = registry.records.get(item.id)
        parent_record = registry.records.get(current.id)
        target = target_record["theme"] if target_record else item.directory
        mother = parent_record["theme"] if parent_record else current.directory
        result.append(Binding(item.id, target, mother, current.id,
                              parent_record["fullname"] if parent_record else current.name,
                              item.name, item.badge, chain))
    return result


def dependencies(definitions):
    # An inherited-only addition creates no theme files, hence no invalidation.
    return [{key: value for key, value in asdict(item).items() if key != "dependencies"}
            for item in sorted(bindings(definitions), key=lambda item: item.id)]
