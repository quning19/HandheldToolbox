"""User-selectable import and export policies."""

from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, Field


class RomMode(StrEnum):
    COPY = "copy"
    MOVE = "move"
    SYMLINK = "symlink"
    LINK = "link"
    HARDLINK = "hardlink"
    NONE = "none"


class MediaMode(StrEnum):
    COPY = "copy"
    SYMLINK = "symlink"
    HARDLINK = "hardlink"


class ConflictPolicy(StrEnum):
    SKIP = "skip"
    OVERWRITE = "overwrite"
    RENAME = "rename"
    ERROR = "error"
    NEWER = "newer"


class ImportOptions(BaseModel):
    calculate_hashes: bool = False
    game_name_field: str = "label"
    platforms: list[str] = Field(default_factory=list)
    metadata_encoding: str = "utf-8-sig"
    source_profile: Path | None = None
    media_path_aliases: dict[str, dict[str, Path]] = Field(default_factory=dict)
    shared_media_root: Path | None = None


class ExportOptions(BaseModel):
    rom_mode: RomMode = RomMode.COPY
    media_mode: MediaMode = MediaMode.COPY
    conflict: ConflictPolicy = ConflictPolicy.SKIP
    in_place: bool = False
    shared_pegasus: bool = False
