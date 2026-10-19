"""Select real launch entries without changing source records or media."""

from pathlib import Path

from retrolibx.adapters.esde.merge import parse_xml, relative_game_path
from retrolibx.core.models import Library
from retrolibx.errors import ValidationError
from retrolibx.utils.discovery import rom_relative_path
from retrolibx.utils.encoding import detect_metadata_encoding
from retrolibx.core.entries import select_entries as select_source_entries, track_files


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


def select_entries(
    library: Library, snapshot: Path, rom_roots: dict[str, str], *,
    policy: str = "merge", existing_only: bool = False,
) -> dict[str, int]:
    if policy not in {"merge", "skip", "replace"}:
        raise ValidationError("Unknown existing-entry policy")
    old = {}
    for system in library.systems:
        target = system.metadata.get("target_system", system.id)
        old[target] = {value.removeprefix("./").casefold()
                       for value in existing_paths(snapshot, target, rom_roots[target])}
    return select_source_entries(library, old, skip_existing=policy == "skip", existing_only=existing_only)
