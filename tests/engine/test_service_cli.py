import hashlib
import json
from pathlib import Path

import pytest
from lxml import etree
from typer.testing import CliRunner

from retrolibx.application import ConversionService
from retrolibx.cli import app
from retrolibx.core.executor import PlanExecutor
from retrolibx.core.operations import WriteText
from retrolibx.core.options import ExportOptions, RomMode
from retrolibx.errors import FileOperationError

runner = CliRunner()


def test_cli_version() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert result.stdout.strip() == "0.1.0"


def retroarch_library(root: Path) -> Path:
    rom = root / "roms/game.gba"
    rom.parent.mkdir(parents=True)
    rom.write_bytes(b"rom")
    root.joinpath("playlists").mkdir()
    root.joinpath("playlists/Nintendo - Game Boy Advance.lpl").write_text(
        json.dumps(
            {
                "items": [
                    {
                        "path": str(rom),
                        "label": "Game",
                        "core_path": "DETECT",
                        "core_name": "DETECT",
                        "crc32": "DETECT",
                        "db_name": "Nintendo - Game Boy Advance.lpl",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    return root


def test_dry_run_does_not_write(tmp_path: Path) -> None:
    source, target = retroarch_library(tmp_path / "source"), tmp_path / "target"
    result = ConversionService().convert(source, target, "rocknix", dry_run=True)
    assert result.plan.actionable_count > 0
    assert result.execution is None
    assert not target.exists()


def test_retroarch_to_rocknix_end_to_end(tmp_path: Path) -> None:
    source, target = retroarch_library(tmp_path / "source"), tmp_path / "target"
    result = ConversionService().convert(source, target, "rocknix")
    assert result.execution is not None
    assert target.joinpath("gba/game.gba").read_bytes() == b"rom"
    assert "<name>Game</name>" in target.joinpath("gba/gamelist.xml").read_text()


def test_cli_detect_json_and_dry_run(tmp_path: Path) -> None:
    source, target = retroarch_library(tmp_path / "source"), tmp_path / "target"
    detected = runner.invoke(app, ["detect", str(source), "--json"])
    assert detected.exit_code == 0
    assert json.loads(detected.stdout)[0]["format"] == "retroarch"
    result = runner.invoke(
        app, ["convert", str(source), "--to", "rocknix", "--output", str(target), "--dry-run"]
    )
    assert result.exit_code == 0, result.output
    assert "Dry run" in result.stdout
    assert not target.exists()


def pegasus_update_source(root: Path) -> Path:
    platform = root / "GBA"
    platform.joinpath("nested").mkdir(parents=True)
    platform.joinpath("nested/a.zip").write_bytes(b"original rom")
    platform.joinpath("b.zip").write_bytes(b"new rom")
    platform.joinpath("metadata.pegasus.txt").write_text(
        "collection: GBA\ngame: Source name\nfile: nested/a.zip\n"
        "description: Source description\nsort-by: 001\nfavorite: true\n\n"
        "game: New game\nfile: b.zip\n",
        encoding="utf-8",
    )
    return root


def test_local_esde_update_merges_user_data_even_with_default_skip(tmp_path: Path) -> None:
    source = pegasus_update_source(tmp_path / "source")
    target = tmp_path / "target"
    gamelist = target / "gamelists/gba/gamelist.xml"
    gamelist.parent.mkdir(parents=True)
    baseline = (
        b"<gameList><game><path>./nested/a.zip</path><name>User name</name>"
        b"<sortname>User sort</sortname><favorite>false</favorite><playcount>7</playcount>"
        b"<lastplayed>20261010T120000</lastplayed><playtime>99</playtime>"
        b"<altemulator>gpSP</altemulator><x-user>keep</x-user><desc/></game>"
        b"<game><path>./extra.zip</path><name>Extra</name></game></gameList>"
    )
    gamelist.write_bytes(baseline)
    service = ConversionService()
    preview = service.convert(source, target, "es-de", source_format="pegasus", dry_run=True)
    write = next(op for op in preview.plan.operations if isinstance(op, WriteText))
    assert not write.skipped and write.backup
    assert write.expected_sha256 == hashlib.sha256(baseline).hexdigest()
    assert gamelist.read_bytes() == baseline
    assert not target.joinpath("ROMs").exists()
    service.convert(source, target, "es-de", source_format="pegasus")
    root = etree.parse(str(gamelist))
    assert len(root.findall("game")) == 3
    for field, value in {
        "name": "User name", "sortname": "User sort", "favorite": "false",
        "playcount": "7", "lastplayed": "20261010T120000", "playtime": "99",
        "altemulator": "gpSP", "x-user": "keep", "desc": "Source description",
    }.items():
        assert root.findtext("game/" + field) == value
    assert gamelist.with_name("gamelist.xml.frontendtrans.bak").read_bytes() == baseline
    assert source.joinpath("GBA/nested/a.zip").read_bytes() == b"original rom"


def test_esde_guard_refuses_changed_list_before_rom_copy(tmp_path: Path) -> None:
    source = pegasus_update_source(tmp_path / "source")
    target = tmp_path / "target"
    gamelist = target / "gamelists/gba/gamelist.xml"
    gamelist.parent.mkdir(parents=True)
    gamelist.write_text("<gameList/>", encoding="utf-8")
    preview = ConversionService().convert(
        source, target, "es-de", source_format="pegasus", dry_run=True
    )
    gamelist.write_text("<gameList><!-- user edited --></gameList>", encoding="utf-8")
    with pytest.raises(FileOperationError, match="changed after planning"):
        PlanExecutor().execute(preview.plan)
    assert not target.joinpath("ROMs").exists()
    assert "user edited" in gamelist.read_text(encoding="utf-8")


def test_esde_no_rom_copy_matches_nested_absolute_source_path(tmp_path: Path) -> None:
    source = pegasus_update_source(tmp_path / "source")
    target = tmp_path / "target"
    gamelist = target / "gamelists/gba/gamelist.xml"
    gamelist.parent.mkdir(parents=True)
    root = etree.Element("gameList")
    game = etree.SubElement(root, "game")
    etree.SubElement(game, "path").text = source.joinpath("GBA/nested/a.zip").as_posix()
    etree.SubElement(game, "name").text = "Existing name"
    gamelist.write_bytes(etree.tostring(root))
    ConversionService().convert(
        source, target, "es-de", source_format="pegasus",
        export_options=ExportOptions(rom_mode=RomMode.NONE),
    )
    result = etree.parse(str(gamelist))
    assert len(result.findall("game")) == 2
    assert result.findtext("game/name") == "Existing name"
    assert not target.joinpath("ROMs").exists()
