"""Select real launch entries without changing source records or media."""

from pathlib import Path, PurePosixPath
import re
import shlex

from retrolibx.adapters.esde.merge import parse_xml, relative_game_path
from retrolibx.core.models import Library
from retrolibx.errors import ValidationError
from retrolibx.utils.discovery import rom_relative_path
from retrolibx.utils.encoding import detect_metadata_encoding


def existing_paths(snapshot: Path, system: str, rom_root: str) -> set[str]:
    path = snapshot / "gamelists" / system / "gamelist.xml"
    if not path.resolve().is_relative_to(snapshot.resolve()):
        raise ValidationError("Gamelist escaped output directory")
    if not path.is_file():
        return set()
    root = parse_xml(path.read_bytes(), "gameList")
    values = [relative_game_path(node.findtext("path") or "", rom_root) for node in root.findall("game")]
    if len(values) != len(set(values)):
        raise ValidationError(f"Duplicate existing ROM entries: {system}")
    return set(values)


def track_files(paths: list[Path]) -> set[Path]:
    """Only files explicitly referenced by disc descriptors are subordinate."""
    result: set[Path] = set()
    for path in paths:
        suffix = path.suffix.casefold()
        if suffix not in {".cue", ".gdi", ".m3u", ".ccd"} or not path.is_file():
            continue
        if suffix == ".ccd":
            result.update(path.with_suffix(ext).resolve() for ext in (".img", ".sub"))
            continue
        raw = path.read_bytes()
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeError:
            text = raw.decode("gb18030")
        names: list[str] = []
        if suffix == ".cue":
            names = [match.group(1) or match.group(2) for match in re.finditer(
                r'^\s*FILE\s+(?:"([^"]+)"|(\S+))\s+', text, re.I | re.M,
            )]
        elif suffix == ".m3u":
            names = [line.strip() for line in text.splitlines() if line.strip() and not line.lstrip().startswith("#")]
        else:
            for line in text.splitlines()[1:]:
                parts = shlex.split(line)
                if len(parts) >= 5:
                    names.append(parts[4])
        for name in names:
            relative = PurePosixPath(name.replace("\\", "/"))
            if relative.is_absolute() or ".." in relative.parts or ":" in name:
                raise ValidationError(f"Unsafe disc track reference: {name}")
            result.add(path.parent.joinpath(*relative.parts).resolve())
    return result


def select_entries(
    library: Library, snapshot: Path, rom_roots: dict[str, str], *,
    policy: str = "merge", existing_only: bool = False,
) -> dict[str, int]:
    """Filter the IR; preserve metadata indices used by shared-media patching."""
    counts = {"missing": 0, "existing": 0, "selected": 0}
    if policy not in {"merge", "skip", "replace"}:
        raise ValidationError("Unknown existing-entry policy")
    missing: set[Path] = set()
    for system in library.systems:
        target = system.metadata.get("target_system", system.id)
        old = existing_paths(snapshot, target, rom_roots[target]) if policy == "skip" else set()
        subordinate = track_files([rom.path for game in system.games for rom in game.roms]) if existing_only else set()
        games = []
        for game in system.games:
            selected = []
            for rom in game.roms:
                if existing_only and not rom.path.is_file():
                    missing.add(rom.path)
                    counts["missing"] += 1
                    continue
                if rom.path.resolve() in subordinate:
                    continue
                key = "./" + rom_relative_path(rom.path, rom.metadata).as_posix()
                if key in old:
                    counts["existing"] += 1
                    continue
                selected.append(rom)
            if selected:
                games.append(game.model_copy(update={"roms": selected}))
                counts["selected"] += len(selected)
        system.games = games
    for diagnostic in library.diagnostics:
        if diagnostic.code == "missing-rom" and diagnostic.path in missing:
            diagnostic.severity = "warning"
    return counts
