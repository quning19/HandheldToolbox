"""Focused shared-entry regressions; temporary libraries, no real device."""

from pathlib import Path
from uuid import uuid4

import pytest
from lxml import etree

from frontend_common.state import default_definitions
from library_converter.desktop import scan_library, convert_library
from library_converter.savedeck import scan_savedeck, convert_savedeck
from retrolibx.adapters.savedeck.document import parse_document, render_document
from retrolibx.application.service import ConversionService
from retrolibx.core.entries import track_files
from retrolibx.core.options import ExportOptions
from retrolibx.errors import ValidationError


def write(root, relative, raw=b"rom"):
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return path


def workflow(root, work, target, full=False):
    scan, convert = (scan_savedeck, convert_savedeck) if target == "savedeck" else (scan_library, convert_library)
    session = scan(work, default_definitions(), str(root), None, lambda: False, lambda *_: None, lambda _: None)
    assert not session.platforms["GBA"].error
    result = convert(session, ["GBA"], False, full, work, lambda: False, lambda *_: None)
    return session, result


@pytest.mark.parametrize("target", ["es-de", "savedeck"])
@pytest.mark.parametrize("full", [False, True])
def test_default_sync_and_full_refresh_preserve_state_and_never_clean_media(tmp_path, target, full):
    root, work = tmp_path / "Roms", tmp_path / "work"
    platform = root / "GBA"
    for name in ("keep.gba", "removed-meta.gba", "removed-rom.gba"):
        write(platform, name)
    media = write(platform, "media/Keep/boxfront.png", b"original")
    meta = write(platform, "metadata.pegasus.txt", (
        "collection: GBA\nlaunch: source old\n"
        "game: Keep\nfile: keep.gba\ndescription: old description\nfavorite: false\nassets.box_front: media/Keep/boxfront.png\n"
        "game: Remove metadata\nfile: removed-meta.gba\n"
        "game: Remove ROM\nfile: removed-rom.gba\n").encode())
    session, _ = workflow(root, work, target)
    config = platform / "savedeck.toml" if target == "savedeck" else session.target / "gamelists/gba/gamelist.xml"
    if target == "savedeck":
        data = parse_document(config.read_bytes())
        keep = data["games"][0]
        identifier = keep["id"]
        keep.update(name="User title", description="User description", favorite=True, play_count=7,
                    last_played="20261019T120000", hidden=True, custom="keep", launch="user command")
        media_target = platform / keep["cover"]
        config.write_text(render_document(data), encoding="utf-8")
    else:
        data = etree.fromstring(config.read_bytes())
        keep = data.find("game[path='./keep.gba']")
        keep.find("name").text = "User title"
        keep.find("desc").text = "User description"
        keep.find("favorite").text = "true"
        for key, value in {"id": str(uuid4()), "playcount": "7", "lastplayed": "20261019T120000", "hidden": "true", "custom": "keep"}.items():
            etree.SubElement(keep, key).text = value
        identifier = keep.findtext("id")
        config.write_bytes(etree.tostring(data))
        media_target = session.target / "downloaded_media/gba/covers/keep.png"
        systems_path = session.target / "custom_systems/es_systems.xml"
        systems = etree.fromstring(systems_path.read_bytes())
        systems.find("system[name='gba']/command").text = "USER_COMMAND %ROM%"
        systems_path.write_bytes(etree.tostring(systems))
    media_target.write_bytes(b"user media")
    retired = write(media_target.parent, "retired.png", b"retired media")
    media.write_bytes(b"updated media")
    (platform / "removed-rom.gba").unlink()
    write(platform, "new.gba")
    write(platform, "unregistered.gba")
    meta.write_text(
        "collection: GBA\nlaunch: source new\n"
        "game: New title\nfile: keep.gba\ndescription: new description\nfavorite: false\nassets.box_front: media/Keep/boxfront.png\n"
        "game: Remove ROM\nfile: removed-rom.gba\n"
        "game: Added\nfile: new.gba\n", encoding="utf-8")
    original = meta.read_bytes()
    _, result = workflow(root, work, target, full)
    assert result["roms"] == (2 if full else 1)
    assert result["removed"] == 2
    assert meta.read_bytes() == original
    assert retired.read_bytes() == b"retired media"
    assert (platform / "removed-meta.gba").is_file()
    if target == "savedeck":
        data = parse_document(config.read_bytes())
        assert {game["file"] for game in data["games"]} == {"keep.gba", "new.gba"}
        keep = next(game for game in data["games"] if game["file"] == "keep.gba")
        assert keep["id"] == identifier
        assert keep["favorite"] is True and keep["hidden"] is True
        assert keep["play_count"] == 7 and keep["last_played"] == "20261019T120000"
        assert keep["custom"] == "keep"
        assert keep["name"] == ("New title" if full else "User title")
        assert keep["description"] == ("new description" if full else "User description")
        assert data["launch"] == ("source new" if full else "source old")
        assert ("launch" not in keep) if full else keep["launch"] == "user command"
        assert (platform / keep["cover"]).read_bytes() == (b"updated media" if full else b"user media")
    else:
        data = etree.fromstring(config.read_bytes())
        assert {game.findtext("path") for game in data.findall("game")} == {"./keep.gba", "./new.gba"}
        keep = data.find("game[path='./keep.gba']")
        assert keep.findtext("id") == identifier
        assert keep.findtext("favorite") == "true" and keep.findtext("hidden") == "true"
        assert keep.findtext("playcount") == "7" and keep.findtext("lastplayed") == "20261019T120000"
        assert keep.findtext("custom") == "keep"
        assert keep.findtext("name") == ("New title" if full else "User title")
        assert keep.findtext("desc") == ("new description" if full else "User description")
        command = etree.fromstring(systems_path.read_bytes()).findtext("system[name='gba']/command")
        assert (command != "USER_COMMAND %ROM%") if full else command == "USER_COMMAND %ROM%"
    if target == "es-de":
        assert media_target.read_bytes() == (b"updated media" if full else b"user media")
    elif full:
        assert media_target.read_bytes() == b"user media"  # Renamed media leaves its old copy intact.


@pytest.mark.parametrize("target", ["es-de", "savedeck"])
def test_descriptor_chain_keeps_outer_entry_and_independent_discs(tmp_path, target):
    source = tmp_path / "PS1"
    write(source, "group.m3u", b"disc.cue\n")
    cue = write(source, "disc.cue", b'FILE "track.bin" BINARY\n')
    track = write(source, "track.bin")
    write(source, "independent.chd")
    write(source, "metadata.pegasus.txt", (
        "collection: PS1\ngame: Group\nfiles:\n  group.m3u\n  track.bin\n"
        "game: Independent\nfile: independent.chd\n").encode())
    assert track_files([source / "group.m3u"]) == {cue, track}
    output = tmp_path / "out"
    ConversionService().convert(source, output, target, source_format="pegasus", export_options=ExportOptions(rom_mode="none"))
    if target == "savedeck":
        games = parse_document((output / "psx/savedeck.toml").read_bytes())["games"]
        assert {game["file"] for game in games} == {"group.m3u", "independent.chd"}
    else:
        games = etree.parse(str(output / "gamelists/psx/gamelist.xml")).findall("game")
        assert {game.findtext("path") for game in games} == {"./group.m3u", "./independent.chd"}


@pytest.mark.parametrize("target", ["es-de", "savedeck"])
def test_invalid_source_blocks_sync_instead_of_removing_old_entries(tmp_path, target):
    source = tmp_path / "GBA"
    write(source, "a.gba")
    meta = write(source, "metadata.pegasus.txt", b"collection: GBA\ngame: A\nfile: a.gba\n")
    output = tmp_path / "out"
    service = ConversionService()
    service.convert(source, output, target, source_format="pegasus", export_options=ExportOptions(rom_mode="none"))
    config = output / ("GBA/savedeck.toml" if target == "savedeck" else "gamelists/gba/gamelist.xml")
    original = config.read_bytes()
    meta.write_bytes(b"collection: GBA\ngame: Invalid no file\n")
    with pytest.raises(ValidationError):
        service.convert(source, output, target, source_format="pegasus", export_options=ExportOptions(rom_mode="none"))
    assert config.read_bytes() == original


def test_savedeck_same_system_in_separate_directories_has_independent_entry_sets(tmp_path):
    source, output = tmp_path / "Roms", tmp_path / "out"
    for folder in ("PackA", "PackB"):
        write(source, folder + "/a.gba")
        write(source, folder + "/metadata.pegasus.txt", b"collection: GBA\ngame: A\nfile: a.gba\n")
    identifier = str(uuid4())
    existing = {"format_version": 1, "platform": "GBA", "games": [
        {"name": "Keep B", "file": "a.gba", "id": identifier, "sort": "000009"}]}
    write(output, "PackB/savedeck.toml", render_document(existing).encode())
    ConversionService().convert(source, output, "savedeck", source_format="pegasus",
                                export_options=ExportOptions(rom_mode="none"))
    first = parse_document((output / "PackA/savedeck.toml").read_bytes())
    assert [game["file"] for game in first["games"]] == ["a.gba"]
    assert parse_document((output / "PackB/savedeck.toml").read_bytes()) == existing
