"""Read-only Pegasus media discovery shared by ES-DE and SaveDeck.

Adapted from PegasusGGameManager metadata/assets.py and asset_check.py:
local file states, candidate directories, role/extension matching and thumbnail
exclusion. Unlike its repair command, this module never edits metadata.
Approved differences: search directory groups in priority order, support absent
references, and select/report the first sorted candidate within a group.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path

from retrolibx.core.models import Diagnostic
from retrolibx.core.source_profiles import SourceProfile


class AssetFiles:
    """PGM's local file-state reader; failed reads are never empty listings."""

    def __init__(self, directory: Path):
        self.root = os.path.abspath(directory)
        self.files: set[str] = set()
        self.states: dict[str, str] = {}
        self.directories: dict[str, list[str] | None] = {}
        found = self._read(self.root, recursive=True)
        self.complete = found is not None
        if found is not None:
            self.files.update(found)

    def _read(self, directory: str, recursive: bool = False) -> list[str] | None:
        try:
            mode = os.stat(directory).st_mode
        except FileNotFoundError:
            return None if recursive else []
        except OSError:
            return None
        try:
            if not stat.S_ISDIR(mode):
                return None
            if recursive:
                found, errors = [], []
                for folder, _, files in os.walk(directory, onerror=errors.append, followlinks=False):
                    for name in files:
                        path = os.path.join(folder, name)
                        if stat.S_ISREG(os.stat(path).st_mode):
                            found.append(path)
                return None if errors else found
            with os.scandir(directory) as entries:
                return [entry.path for entry in entries if entry.is_file()]
        except OSError:
            return None

    def state(self, path: Path) -> str:
        value = os.path.normpath(path)
        if value in self.files:
            return "present"
        if value not in self.states:
            try:
                self.states[value] = "present" if stat.S_ISREG(os.stat(value).st_mode) else "unknown"
            except FileNotFoundError:
                self.states[value] = "missing"
            except OSError:
                self.states[value] = "unknown"
        return self.states[value]

    def children(self, directory: str) -> list[str] | None:
        if directory not in self.directories:
            try:
                inside = os.path.commonpath([self.root, directory]) == self.root
            except ValueError:
                inside = False
            if inside and self.complete:
                self.directories[directory] = sorted(p for p in self.files if os.path.dirname(p) == directory)
            else:
                self.directories[directory] = self._read(directory)
                self.files.update(self.directories[directory] or [])
        return self.directories[directory]


def _inside_platform(path: Path, root: Path) -> bool:
    resolved = path.resolve()
    return resolved.is_relative_to(root) and not any(
        (parent / "metadata.pegasus.txt").is_file()
        for parent in resolved.parents if parent != root and parent.is_relative_to(root)
    )


def _label_folder(root: Path, directory: str, name: str) -> set[str]:
    # PGM treats titles as labels, never as arbitrary paths.
    if not name or name in (".", "..") or any(c in name for c in "/\\\x00\r\n"):
        return set()
    return {str(root / directory / name)}


def discover_media(
    files: AssetFiles, game: str, roms: list[Path], assets: dict[str, Path],
    profile: SourceProfile, metadata: Path, diagnostics: list[Diagnostic],
) -> dict[str, Path]:
    """Keep valid references and fill missing/invalid roles without source edits."""
    result = dict(assets)
    present_roms = [path for path in roms if files.state(path) == "present"]
    if not present_roms:
        return result
    root = Path(files.root).resolve()
    # Use original valid assets, not earlier discoveries: role order must not
    # change which directories are eligible for the fourth priority group.
    other_folders = {str(path.parent) for path in assets.values() if files.state(path) == "present"}
    for role, basenames in profile.media_fallbacks.items():
        original = assets.get(role)
        state = files.state(original) if original is not None else "missing"
        if state == "present":
            continue
        details = {"role": role, "reference": str(original) if original else None}
        if state == "unknown" or not files.complete:
            diagnostics.append(Diagnostic(
                severity="warning", code="unknown-media", path=metadata, game_name=game,
                message=f"{game}: {role} 文件状态或目录清单未知，未自动选择媒体", details=details,
            ))
            continue
        original_value = str(original) if original is not None else None
        original_folders = {str(original.parent)} if original is not None else set()
        if original is not None:
            original_folders.update(os.path.dirname(p) for p in files.files
                                    if os.path.dirname(p).casefold() == str(original.parent).casefold())
        groups = [
            original_folders,
            _label_folder(root, profile.media_directory, game),
            set().union(*(_label_folder(root, profile.media_directory, path.stem) for path in present_roms)),
            other_folders,
        ]
        names = basenames if isinstance(basenames, list) else [basenames]
        names = {name.lower() for name in names}
        # Same extensions as PGM's ASSET_SPECS candidate matcher.
        extensions = ("mp4", "webm", "mkv", "avi", "mov") if role == "video" else ("png", "jpg", "jpeg", "webp")
        visited: set[str] = set()
        selected = False
        for priority, folders in enumerate(groups, 1):
            found: dict[str, str] = {}
            complete = True
            for folder in sorted(folders - visited):
                visited.add(folder)
                if not _inside_platform(Path(folder), root):
                    continue
                children = files.children(folder)
                if children is None:
                    complete = False
                    continue
                for path in children:
                    if not _inside_platform(Path(path), root):
                        continue
                    stem, ext = os.path.splitext(os.path.basename(path))
                    case_only = original_value is not None and path.casefold() == original_value.casefold()
                    same_role = stem.lower() in names and ext.lower().lstrip(".") in extensions
                    same_stem = (original is not None
                                 and os.path.dirname(path).casefold() == str(original.parent).casefold()
                                 and stem.casefold() == original.stem.casefold()
                                 and ext.lower().lstrip(".") in extensions)
                    if case_only or same_role or same_stem:
                        found[path] = ("仅路径大小写不同" if case_only else
                                       "原目录同名素材扩展名不同" if same_stem else "游戏素材目录内同用途文件")
            if not complete:
                diagnostics.append(Diagnostic(
                    severity="warning", code="unknown-media", path=metadata, game_name=game,
                    message=f"{game}: {role} 第 {priority} 级目录读取不完整，未自动选择媒体",
                    details={**details, "priority": priority},
                ))
                selected = True  # Do not fall through to a lower priority group.
                break
            if not found:
                continue
            candidates = sorted(found)
            chosen = candidates[0]
            result[role] = Path(chosen).resolve()
            decision = {**details, "priority": priority, "selected": chosen,
                        "candidates": [{"path": path, "reason": found[path]} for path in candidates]}
            if len(candidates) > 1:
                diagnostics.append(Diagnostic(
                    severity="warning", code="multiple-media-candidates", path=metadata, game_name=game,
                    message=f"{game}: {role} 第 {priority} 级有多个候选，已选择 {chosen}；候选：" + "、".join(candidates),
                    details=decision,
                ))
            if original is not None:
                diagnostics.append(Diagnostic(
                    severity="info", code="repaired-media-reference", path=metadata, game_name=game,
                    message=f"{game}: {original} -> {chosen}", details=decision,
                ))
            selected = True
            break
        if not selected:
            diagnostics.append(Diagnostic(
                severity="warning", code="missing-media", path=metadata, game_name=game,
                message=f"{game}: {role} 未找到媒体候选", details=details,
            ))
    return result
