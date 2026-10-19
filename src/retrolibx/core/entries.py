"""Shared source-entry selection, independent of target list formats."""

from pathlib import Path, PurePosixPath
import re
import shlex

from .models import Library
from retrolibx.errors import ValidationError
from retrolibx.utils.discovery import rom_relative_path


DISC_EXTENSIONS = {".cue", ".gdi", ".m3u", ".ccd"}


def track_files(paths: list[Path]) -> set[Path]:
    """Follow descriptor chains without requiring all dependencies to exist."""
    result: set[Path] = set()
    visited: set[Path] = set()

    def visit(path: Path, ancestors: set[Path]) -> None:
        path = path.resolve()
        if path in ancestors:
            raise ValidationError(f"Circular disc descriptor reference: {path}")
        if path in visited or path.suffix.casefold() not in DISC_EXTENSIONS or not path.is_file():
            return
        visited.add(path)
        if path.suffix.casefold() == ".ccd":
            result.update(path.with_suffix(ext) for ext in (".img", ".sub"))
            return
        raw = path.read_bytes()
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeError:
            text = raw.decode("gb18030")
        if path.suffix.casefold() == ".cue":
            names = [match.group(1) or match.group(2) for match in re.finditer(
                r'^\s*FILE\s+(?:"([^"]+)"|(\S+))\s+', text, re.I | re.M)]
        elif path.suffix.casefold() == ".m3u":
            names = [line.strip() for line in text.splitlines() if line.strip() and not line.lstrip().startswith("#")]
        else:
            names = []
            for line in text.splitlines()[1:]:
                parts = shlex.split(line)
                if len(parts) >= 5:
                    names.append(parts[4])
        for name in names:
            relative = PurePosixPath(name.replace("\\", "/"))
            if relative.is_absolute() or ".." in relative.parts or ":" in name:
                raise ValidationError(f"Unsafe disc track reference: {name}")
            target = path.parent.joinpath(*relative.parts).resolve()
            result.add(target)
            visit(target, ancestors | {path})

    for path in paths:
        visit(path, set())
    return result


def select_entries(
    library: Library, existing: dict[str, set[str]] | None = None, *,
    skip_existing: bool = False, existing_only: bool = True,
) -> dict[str, int]:
    """Record the complete valid set before optionally selecting only additions."""
    counts = {"missing": 0, "existing": 0, "selected": 0, "removed": 0}
    missing: set[Path] = set()
    for system in library.systems:
        target = system.metadata.get("target_system", system.id)
        old = (existing or {}).get(target, set())
        subordinate = track_files([rom.path for game in system.games for rom in game.roms]) if existing_only else set()
        valid = []
        games = []
        for game in system.games:
            available = []
            for rom in game.roms:
                if existing_only and not rom.path.is_file():
                    missing.add(rom.path)
                    counts["missing"] += 1
                elif rom.path.resolve() not in subordinate:
                    available.append(rom)
            selected = []
            for rom in available:
                key = rom_relative_path(rom.path, rom.metadata).as_posix()
                valid.append(key)
                if skip_existing and key.casefold() in old:
                    counts["existing"] += 1
                else:
                    selected.append(rom)
            if selected:
                games.append(game.model_copy(update={
                    "roms": selected,
                    "source_metadata": {**game.source_metadata, "valid_rom_count": len(available)},
                }))
                counts["selected"] += len(selected)
        system.metadata["valid_rom_paths"] = valid
        counts["removed"] += len(old - {path.casefold() for path in valid})
        system.games = games
    for diagnostic in library.diagnostics:
        if diagnostic.code == "missing-rom" and diagnostic.path in missing:
            diagnostic.severity = "warning"
    return counts


def user_state_field(name: str) -> bool:
    """Identity and play state survive even a full source refresh."""
    normalized = name.casefold().removeprefix("x_pegasus_").replace("_", "").replace("-", "")
    return normalized in {"id", "uuid", "favorite", "favourite", "hidden",
                          "playcount", "lastplayed", "playtime", "completed"}
