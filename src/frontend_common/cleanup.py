"""Explicit local cleanup of known staging, recovery batches and historical logs."""
from dataclasses import dataclass, field
import hashlib
from pathlib import Path
import shutil

from .locking import workspace_lock

CATEGORIES = {"temp": "临时文件", "backups": "备份与恢复资料", "logs": "历史日志"}


@dataclass
class CleanupItem:
    category: str
    relative: str
    files: int
    bytes: int
    signature: str
    latest: bool = False
    details: list = field(default_factory=list)


def inventory(workspace: Path, path: Path, category: str):
    root = workspace.resolve()
    if not path.resolve().is_relative_to(root) or path.resolve() == root:
        raise ValueError("清理路径超出工作目录")
    files = [] if path.is_file() else sorted(path.rglob("*"))
    details, total = [], 0
    signature = hashlib.sha256()
    for entry in [path, *files]:
        if entry.is_symlink() or entry.is_junction() or not entry.resolve().is_relative_to(root):
            raise ValueError("清理目录包含链接或越界路径，已保留：" + str(entry))
        stat = entry.stat()
        relative = entry.relative_to(root).as_posix()
        signature.update(f"{relative}\0{stat.st_size}\0{stat.st_mtime_ns}\n".encode("utf-8"))
        if entry.is_file():
            details.append(relative)
            total += stat.st_size
    return CleanupItem(category, path.relative_to(root).as_posix(), len(details), total, signature.hexdigest(), details=details)


def preview_cleanup(workspace):
    root = Path(workspace).resolve()
    result, retained = [], []
    temp = root / "temp"
    if temp.is_dir():
        for path in sorted(temp.iterdir()):
            if path.is_dir() and (path / ".frontendtrans-temporary").is_file():
                try:
                    result.append(inventory(root, path, "temp"))
                except ValueError as exc:
                    retained.append(str(exc))
            else:
                retained.append("用途未登记，保留：" + path.relative_to(root).as_posix())
    backups = root / "backups"
    if backups.is_dir():
        for group in sorted(backups.iterdir()):
            if not group.is_dir() or group.is_symlink() or group.is_junction():
                retained.append("非批次备份，保留：" + group.name)
                continue
            batches = sorted(group.iterdir(), key=lambda p: p.stat().st_mtime_ns, reverse=True)
            for index, path in enumerate(batches):
                try:
                    item = inventory(root, path, "backups")
                except ValueError as exc:
                    retained.append(str(exc))
                    continue
                item.latest = index == 0
                result.append(item)
    logs = root / "logs"
    if logs.is_dir():
        for path in sorted(logs.iterdir()):
            if path.is_file() and path.name != "desktop.log":
                try:
                    result.append(inventory(root, path, "logs"))
                except ValueError as exc:
                    retained.append(str(exc))
    return result, retained


def clean_workspace(workspace, selected, *, locked=False):
    if not locked:
        with workspace_lock(workspace):
            return clean_workspace(workspace, selected, locked=True)
    current, _retained = preview_cleanup(workspace)
    allowed = {item.relative: item for item in current}
    # Recheck the entire selection before deleting the first entry.
    for item in selected:
        now = allowed.get(item.relative)
        if now is None or now.signature != item.signature or now.category != item.category:
            raise ValueError("清理预览后文件已变化，请刷新预览：" + item.relative)
    removed = []
    for item in selected:
        path = Path(workspace).resolve() / item.relative
        # inventory resolves all descendants and rejects junctions immediately before deletion.
        if inventory(Path(workspace).resolve(), path, item.category).signature != item.signature:
            raise ValueError("待清理文件已变化：" + item.relative)
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()
        removed.append(item.relative)
    return {"message": f"已清理 {len(removed)} 项，共 {sum(item.bytes for item in selected):,} 字节。", "removed": removed}
