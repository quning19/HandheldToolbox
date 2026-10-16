"""A missing relative ROM must not borrow a different version's same-name file."""
from pathlib import Path

import pytest

from retrolibx.adapters.pegasus.adapter import PegasusAdapter
from retrolibx.core.options import ImportOptions
from retrolibx.registry import SystemRegistry


@pytest.mark.parametrize("selected", [False, True])
@pytest.mark.parametrize("missing", [
    "English/game.zip", "./English/game.zip", r"English\game.zip",
    "English/disc/game.zip", "game.zip",
])
def test_missing_relative_rom_keeps_its_path(tmp_path: Path, selected: bool, missing: str):
    root = tmp_path / "library"
    platform = root / "GBA"
    present = platform / "Chinese/disc/game.zip"
    present.parent.mkdir(parents=True)
    present.write_bytes(b"actual selected version")
    # Even a same-name file directly under the wider library root is not a
    # substitute for a reference relative to this metadata's platform directory.
    (root / "game.zip").write_bytes(b"unrelated root file")
    metadata = platform / "metadata.pegasus.txt"
    metadata.write_text(
        "collection: GBA\ngame: Chinese\nfile: Chinese/disc/game.zip\n\n"
        f"game: English\nfile: {missing}\n", encoding="utf-8",
    )
    original = metadata.read_bytes()
    options = ImportOptions(platforms=["GBA"] if selected else [])
    games = PegasusAdapter(SystemRegistry.load()).import_library(root, options).library.systems[0].games
    assert games[0].roms[0].path == present.resolve()
    absent = games[1].roms[0]
    assert absent.path == (platform / missing.replace("\\", "/")).resolve()
    assert not absent.path.is_file()
    assert absent.metadata["source_path"] == missing
    assert metadata.read_bytes() == original


@pytest.mark.parametrize("old_path", [
    "/storage/old/ROMs/GBA/game.zip", "Z:/old/ROMs/GBA/game.zip",
    r"Z:\old\ROMs\GBA\game.zip",
])
def test_rooted_rom_reference_still_relocates(tmp_path: Path, old_path: str):
    root = tmp_path / "GBA"
    rom = root / "content/game.zip"
    rom.parent.mkdir(parents=True)
    rom.write_bytes(b"rom")
    (root / "metadata.pegasus.txt").write_text(
        f"collection: GBA\ngame: Moved\nfile: {old_path}\n", encoding="utf-8",
    )
    game = PegasusAdapter(SystemRegistry.load()).import_library(root, ImportOptions()).library.systems[0].games[0]
    assert game.roms[0].path == rom.resolve()
