import shutil
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest
from lxml import etree

import frontend_platforms
from frontend_platforms import PlatformRegistry, platform_component
from retrolibx.adapters.pegasus.adapter import PegasusAdapter
from retrolibx.application.handheld import HandheldConfig, build_handheld
from retrolibx.core.options import ImportOptions
from retrolibx.registry import SystemRegistry


def test_verified_names_directories_and_hack_recognition() -> None:
    registry = PlatformRegistry.load()
    assert len(registry.records) == 76
    hack = registry.identify("GBA hack", "gba")
    assert hack is not None
    assert hack["name"] == "GBA HACK"
    assert hack["theme"] == hack["rom_directory"] == "GBA hack"
    assert hack["base_platform"] == "gba"
    assert registry.is_hack("GBA hack")
    assert registry.is_hack("FC hack")
    assert registry.is_hack("MD hack(picodrive)")
    assert not registry.is_hack("GBA vib")
    assert not registry.is_hack("random hack")
    wii = registry.resolve("wii")
    assert wii is not None
    assert ET.tostring(registry.system_element(wii)).find(b"%ROMPATH%/WII") >= 0
    shared = SystemRegistry.load()
    assert shared.resolve("GBA hack").id == "GBA HACK"  # type: ignore[union-attr]
    assert shared.resolve("GBA vib").id == "GBA vib"  # type: ignore[union-attr]
    assert "gbah" not in shared.records and "gbavib" not in shared.records
    assert shared.resolve("PS1").id == "psx"  # type: ignore[union-attr]
    assert shared.resolve("Sony PlayStation").id == "psx"  # type: ignore[union-attr]
    assert shared.resolve("MD hack").id == "MD hack"  # type: ignore[union-attr]
    assert shared.resolve("MD hack(picodrive)").id == "MD hack(picodrive)"  # type: ignore[union-attr]


def test_real_hack_directory_wins_and_default_system_definition_is_preserved(
    tmp_path: Path,
) -> None:
    source = tmp_path / "Roms/GBA hack"
    source.mkdir(parents=True)
    (source / "game.zip").write_bytes(b"rom")
    (source / "metadata.pegasus.txt").write_text(
        "collection: GBA\nshortname: gba\ngame: Test\nfile: game.zip\n", encoding="utf-8"
    )
    library = (
        PegasusAdapter(SystemRegistry.load())
        .import_library(source.parent, ImportOptions(platforms=["GBA hack"]))
        .library
    )
    assert library.systems[0].id == "GBA HACK"
    config = HandheldConfig(
        source_root=source.parent,
        device_rom_root="/storage/emulated/0/Test/Roms",
        esde_root="/storage/emulated/0/Test/ES-DE",
        target_empty=True,
    )
    output = tmp_path / "job"
    assert build_handheld(config, ["GBA hack"], output)["executable"]
    assert (output / "files/gamelists/GBA HACK/gamelist.xml").is_file()
    root = etree.parse(str(output / "files/custom_systems/es_systems.xml"))
    assert root.findtext("system[name='GBA HACK']/path") == config.device_rom_root + "/GBA hack"
    assert root.findtext("system[name='GBA HACK']/theme") == "GBA hack"
    assert root.findtext("system[name='GBA HACK']/platform") == "GBA hack"
    original = PlatformRegistry.load().records["GBA HACK"]
    assert [(c.attrib, c.text) for c in root.findall("system[name='GBA HACK']/command")] == [
        (c["attributes"], c["text"]) for c in original["commands"]
    ]
    # Existing tested identifiers containing spaces are accepted and preserved.
    snapshot = tmp_path / "snapshot/custom_systems"
    snapshot.mkdir(parents=True)
    existing = root.getroot()
    etree.SubElement(existing.find("system[name='GBA HACK']"), "user-setting").text = "keep"
    (snapshot / "es_systems.xml").write_bytes(etree.tostring(existing))
    config.target_snapshot = snapshot.parent
    reused = tmp_path / "reused"
    assert build_handheld(config, ["GBA hack"], reused)["executable"]
    merged = etree.parse(str(reused / "files/custom_systems/es_systems.xml"))
    assert merged.findtext("system[name='GBA HACK']/user-setting") == "keep"
    assert library.systems[0].id == "GBA HACK"


def test_platform_names_allow_spaces_but_reject_path_syntax() -> None:
    assert platform_component("MD hack(picodrive)") == "MD hack(picodrive)"
    for value in ["", "..", "../GBA", "GBA/hack", "GBA\\hack", "GBA\nhack", " GBA", "GBA."]:
        with pytest.raises(ValueError):
            platform_component(value)


def test_platform_registry_rejects_ambiguous_aliases_and_invalid_bases() -> None:
    source = PlatformRegistry.load().records["gba"]
    first = {**source, "aliases": ["ambiguous"]}
    second = {
        **source,
        "name": "Other",
        "rom_directory": "Other",
        "theme": "Other",
        "aliases": ["ambiguous"],
    }
    registry = PlatformRegistry({"version": 1, "platforms": [first, second]})
    with pytest.raises(ValueError, match="Ambiguous"):
        registry.resolve("ambiguous")
    with pytest.raises(ValueError, match="Unknown base"):
        PlatformRegistry({"version": 1, "platforms": [{**source, "base_platform": "missing"}]})


def test_xml_changes_drive_recognition_and_android_output_from_one_source(tmp_path: Path) -> None:
    directory = tmp_path / "platform-config"
    shutil.copytree(Path(frontend_platforms.__file__).with_name("custom_systems-PG"), directory)
    xml = directory / "es_systems.xml"
    root = ET.parse(xml)
    gba = root.find("system[name='gba']")
    assert gba is not None
    gba.find("path").text = "%ROMPATH%/GBA custom"  # type: ignore[union-attr]
    gba.find("theme").text = "gba-custom"  # type: ignore[union-attr]
    gba.find("command").set("label", "User core")  # type: ignore[union-attr]
    ET.SubElement(gba, "user-setting").text = "keep"
    root.write(xml, encoding="utf-8", xml_declaration=True)
    registry = PlatformRegistry.load(config_dir=directory)
    record = registry.resolve("GBA custom")
    assert record is not None and record["name"] == "gba"
    assert record["theme"] == "gba-custom"
    assert registry.system_element(record).findtext("user-setting") == "keep"
    source = tmp_path / "Roms/GBA custom"
    source.mkdir(parents=True)
    source.joinpath("a.zip").write_bytes(b"rom")
    source.joinpath("metadata.pegasus.txt").write_text(
        "collection: GBA\ngame: A\nfile: a.zip\n", encoding="utf-8"
    )
    config = HandheldConfig(
        source_root=source.parent, device_rom_root="/storage/Test/Roms",
        esde_root="/storage/Test/ES-DE", target_empty=True, platform_config_dir=directory,
    )
    output = tmp_path / "task"
    assert build_handheld(config, ["GBA custom"], output)["executable"]
    generated = ET.parse(output / "files/custom_systems/es_systems.xml")
    assert len(generated.findall("system")) == 76
    assert generated.findtext("system[name='gba']/path") == "/storage/Test/Roms/GBA custom"
    assert generated.findtext("system[name='gba']/theme") == "gba-custom"
    commands = generated.findall("system[name='gba']/command")
    assert commands[0].get("label") == "User core"
    assert [(c.attrib, c.text) for c in commands] == [(c.attrib, c.text) for c in gba.findall("command")]
    assert generated.findtext("system[name='gba']/user-setting") == "keep"


def test_explicit_missing_platform_directory_does_not_use_bundled_defaults(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="directory is missing"):
        PlatformRegistry.load(config_dir=tmp_path / "missing")
    directory = tmp_path / "partial"
    directory.mkdir()
    directory.joinpath("es_systems.xml").write_text("<systemList/>", encoding="utf-8")
    with pytest.raises(ValueError, match="file is missing"):
        PlatformRegistry.load(config_dir=directory)
