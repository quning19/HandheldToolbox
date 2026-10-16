"""Supported file formats for cover, logo and video conversion."""

import hashlib
from pathlib import Path

IMAGE_ROLES = {"box_front", "logo", "marquee"}
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}
VIDEO_SUFFIXES = {".mp4", ".mkv", ".avi", ".wmv", ".mov", ".webm"}


def supported_media(path: Path, role: str) -> bool:
    suffix = path.suffix.casefold()
    if role in IMAGE_ROLES:
        return suffix in IMAGE_SUFFIXES
    if role == "video":
        return suffix in VIDEO_SUFFIXES
    return True


def file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
