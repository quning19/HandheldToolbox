"""Headless task cancellation and managed staging directories."""
from datetime import datetime
from pathlib import Path
import uuid


class Cancelled(Exception):
    pass


def checkpoint(cancelled) -> None:
    if cancelled():
        raise Cancelled("已取消操作；已经写入的文件保留。")


def new_job(workspace: Path, kind: str) -> Path:
    recovery = kind in {"scan", "convert", "savedeck-scan", "savedeck-export"}
    parent = workspace / "backups/library" if recovery else workspace / "temp"
    path = parent / (kind + "-" + datetime.now().strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:8])
    path.mkdir(parents=True, exist_ok=False)
    # Only staging directories created by this API are eligible for temporary cleanup.
    marker = ".frontendtrans-recovery" if recovery else ".frontendtrans-temporary"
    (path / marker).write_text("1\n", encoding="utf-8")
    return path
