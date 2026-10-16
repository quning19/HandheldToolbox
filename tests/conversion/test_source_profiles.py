import json
from pathlib import Path

import pytest
from lxml import etree

from retrolibx.adapters.esde.adapter import ESDEAdapter
from retrolibx.adapters.pegasus.adapter import PegasusAdapter
from library_converter.handheld import HandheldConfig, build_handheld
from retrolibx.core.options import ExportOptions, ImportOptions
from retrolibx.core.source_profiles import SourceProfile
from retrolibx.errors import ValidationError
from retrolibx.registry import SystemRegistry


PROFILES = Path(__file__).parents[2] / "src/retrolibx/profiles"


def test_configurable_media_fallback_and_explicit_asset_priority(tmp_path: Path) -> None:
    source = tmp_path / "GBA"
    folder = source / "art/Game"
    folder.mkdir(parents=True)
    for name in ["front.png", "badge.png", "preview.mp4"]:
        folder.joinpath(name).write_bytes(b"media")
    source.joinpath("a.zip").write_bytes(b"rom")
    metadata = source / "metadata.pegasus.txt"
    metadata.write_text("collection: GBA\ngame: Game\nfile: a.zip\n", encoding="utf-8")
    profile_file = tmp_path / "source-profile.json"
    profile_file.write_text(json.dumps({
        "name": "custom-media", "media_directory": "art",
        "media_fallbacks": {"box_front": "front", "logo": "badge", "video": "preview"},
    }), encoding="utf-8")
    adapter = PegasusAdapter(SystemRegistry.load())
    generic = adapter.import_library(source, ImportOptions()).library.systems[0].games[0]
    assert generic.media.box_front is None and generic.media.video is None
    configured = adapter.import_library(
        source, ImportOptions(source_profile=profile_file)
    ).library.systems[0].games[0]
    assert configured.media.box_front == folder.joinpath("front.png")
    assert configured.media.logo == folder.joinpath("badge.png")
    assert configured.media.video == folder.joinpath("preview.mp4")
    source.joinpath("selected.png").write_bytes(b"selected")
    metadata.write_text(
        metadata.read_text(encoding="utf-8") + "assets.box_front: selected.png\n",
        encoding="utf-8",
    )
    configured = adapter.import_library(
        source, ImportOptions(source_profile=profile_file)
    ).library.systems[0].games[0]
    assert configured.media.box_front == source.joinpath("selected.png")
    profile_file.write_text('{"media_directory":"../outside"}', encoding="utf-8")
    with pytest.raises(ValidationError, match="inside the source platform"):
        SourceProfile.load(profile_file)


def test_version_note_is_profile_specific_and_raw_source_is_preserved(tmp_path: Path) -> None:
    source = tmp_path / "GBA"
    source.mkdir()
    source.joinpath("a.zip").write_bytes(b"rom")
    source.joinpath("b.zip").write_bytes(b"rom")
    metadata = source / "metadata.pegasus.txt"
    metadata.write_text(
        "collection: GBA\ngame: Example\nfile: a.zip\ndeveloper: Example v2\n"
        "description: Description\n\ngame: Other\nfile: b.zip\ndeveloper: Camelot\n",
        encoding="utf-8",
    )
    original = metadata.read_bytes()
    registry = SystemRegistry.load()
    adapter = PegasusAdapter(registry)
    generic = adapter.import_library(source, ImportOptions()).library
    assert generic.systems[0].games[0].developer == "Example v2"
    assert generic.systems[0].games[0].description == "Description"
    configured = adapter.import_library(
        source, ImportOptions(source_profile=PROFILES / "pegasus-g.json")
    ).library
    game = configured.systems[0].games[0]
    assert game.developer is None
    assert game.description == "Description\n\n版本说明: Example v2"
    assert game.source_metadata["pegasus_fields"]["developer"] == ["Example v2"]
    assert configured.systems[0].games[1].developer == "Camelot"
    intent = ESDEAdapter(registry).render_library(configured, tmp_path / "out", ExportOptions())
    root = etree.fromstring(intent.texts[0].content.encode("utf-8"))
    assert root.findtext("game/desc").count("版本说明") == 1
    assert root.findall("game")[1].findtext("developer") == "Camelot"
    assert metadata.read_bytes() == original


def test_vib_confirmation_keeps_verified_commands_without_forcing_core_name(tmp_path: Path) -> None:
    source = tmp_path / "Roms/GBA vib"
    source.mkdir(parents=True)
    source.joinpath("a.zip").write_bytes(b"rom")
    source.joinpath("metadata.pegasus.txt").write_text(
        "collection: GBA vib\nlaunch: custom-core-name {file.path}\ngame: A\nfile: a.zip\n",
        encoding="utf-8",
    )
    config = HandheldConfig(
        source_root=source.parent, device_rom_root="/storage/Test/Roms",
        esde_root="/storage/Test/ES-DE", target_empty=True,
    )
    blocked = tmp_path / "blocked"
    assert not build_handheld(config, ["GBA vib"], blocked)["executable"]
    assert not blocked.joinpath("apply.sh").exists()
    config.confirmed_systems = ["GBA vib"]
    output = tmp_path / "confirmed"
    assert build_handheld(config, ["GBA vib"], output)["executable"]
    commands = etree.parse(str(output / "files/custom_systems/es_systems.xml")).findall(
        "system[name='GBA vib']/command"
    )
    original = SystemRegistry.load().records["GBA vib"].definition["commands"]
    assert [(dict(c.attrib), c.text) for c in commands] == [
        (c["attributes"], c["text"]) for c in original
    ]
    assert "gpsp_libretro_android.so" in commands[0].text
    assert config.launch_overrides == {}
    profile_file = tmp_path / "verified-source.json"
    profile_file.write_text('{"name":"verified-vib","confirmation_systems":[]}', encoding="utf-8")
    config.source_profile = profile_file
    config.confirmed_systems = []
    assert build_handheld(config, ["GBA vib"], tmp_path / "no-extra-confirmation")["executable"]
