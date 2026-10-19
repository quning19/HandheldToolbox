"""SaveDeck documents, identity preservation and config/media export plans."""

from copy import deepcopy
from pathlib import Path, PurePosixPath
from uuid import NAMESPACE_URL, UUID, uuid5

import pytest

from retrolibx.adapters.savedeck.adapter import SaveDeckAdapter
from retrolibx.adapters.savedeck.document import (
    merge_documents, parse_document, render_document,
)
from retrolibx.adapters.savedeck.merge import merge_lists
from retrolibx.core.models import Game, LaunchConfig, Library, Media, Rom, System
from retrolibx.core.operations import ExportIntent, TextRequest
from retrolibx.core.options import ExportOptions, ImportOptions
from retrolibx.errors import ParseError, ValidationError
from retrolibx.registry import SystemRegistry


def document():
    return {"format_version": 1, "platform": "GBA", "games": [
        {"name": "游戏", "file": "rom/游戏.gba", "id": str(uuid5(NAMESPACE_URL, "test"))},
    ]}


def test_document_round_trip_multiline_and_unknown_fields():
    data = document()
    data["games"][0].update(description='第一行\n第二行 "说明" \\ 路径 🎮\x7f', custom={"tag": [True, "中文"]})
    assert parse_document(render_document(data).encode("utf-8")) == data
    assert parse_document(render_document({"platform": "GBA", "games": []}).encode()) == {
        "platform": "GBA", "games": [],
    }


@pytest.mark.parametrize("reference", ["/rom/a.gba", "../a.gba", "D:/a.gba", "https://example/a", "rom\\a.gba", "./a.gba"])
def test_document_rejects_nonportable_paths(reference):
    data = document()
    data["games"][0]["file"] = reference
    with pytest.raises(ValidationError):
        render_document(data)


def test_document_rejects_case_only_duplicates_and_duplicate_ids():
    data = document()
    other = deepcopy(data["games"][0])
    other["file"] = "ROM/游戏.gba"
    data["games"].append(other)
    with pytest.raises(ValidationError, match="路径重复"):
        render_document(data)
    other["file"] = "another.gba"
    with pytest.raises(ValidationError, match="ID"):
        render_document(data)


def test_merge_preserves_user_changes_ids_order_and_unknown_fields():
    old = document()
    old["sort"] = "002"
    old["games"][0].update(name="用户改名", description="", sort="006", launch="custom launch", custom="keep")
    new = document()
    new["games"][0].update(id=str(uuid5(NAMESPACE_URL, "new")), description="补充资料", launch="new launch")
    new["games"].append({"name": "新增", "file": "new.gba"})
    merged = merge_documents(old, new)
    assert merged["sort"] == "002"
    assert merged["games"][0] == dict(old["games"][0], description="补充资料")
    assert merged["games"][1] == new["games"][1]
    replaced = merge_documents(old, new, replace=True)
    assert replaced["games"][0]["name"] == "游戏"
    assert replaced["games"][0]["id"] == old["games"][0]["id"]
    assert replaced["games"][0]["custom"] == "keep"
    assert old["games"][0]["description"] == ""


def test_merge_captures_baseline_and_requests_backup(tmp_path):
    source = tmp_path / "source"
    (source / "rom").mkdir(parents=True)
    (source / "rom/游戏.gba").write_bytes(b"rom")
    target = tmp_path / "out"
    config = target / "GBA/savedeck.toml"
    config.parent.mkdir(parents=True)
    config.write_text(render_document(document()), encoding="utf-8")
    intent = ExportIntent(texts=[TextRequest(destination=PurePosixPath("GBA/savedeck.toml"), content=render_document(document()))])
    merge_lists(intent, target, source_roots={"GBA": source})
    assert intent.texts[0].backup
    assert len(intent.texts[0].expected_sha256) == 64


def test_adapter_reuses_nested_roms_and_generates_official_media_and_launch(tmp_path):
    source = tmp_path / "source"
    rom = source / "discs/game.m3u"
    rom.parent.mkdir(parents=True)
    rom.write_text("disc1.cue\n", encoding="utf-8")
    (rom.parent / "disc1.cue").write_text('FILE "disc1.bin" BINARY\n', encoding="utf-8")
    (rom.parent / "disc1.bin").write_bytes(b"rom")
    cover = source / "cover.webp"
    cover.write_bytes(b"cover")
    library = Library(format="pegasus", systems=[System(
        id="psx", name="PSX", metadata={"source_root": str(source), "source_platform": "PS 包", "pegasus": {"launch": ["default command"]}},
        games=[Game(name="游戏", roms=[Rom(path=rom, metadata={"relative_path": "discs/game.m3u"})],
                    media=Media(box_front=cover), launch=LaunchConfig(command="game command"))],
    )])
    adapter = SaveDeckAdapter(SystemRegistry.load())
    intent = adapter.render_library(library, tmp_path / "out", ExportOptions())
    data = parse_document(intent.texts[0].content.encode())
    assert data["launch"] == "default command"
    assert data["games"][0]["launch"] == "game command"
    assert data["games"][0]["file"] == "discs/game.m3u"
    assert data["games"][0]["cover"] == "media/游戏/cover.webp"
    assert data["games"][0]["sort"] == "000001"
    assert len(intent.files) == 1 and intent.files[0].category == "media"
    assert intent.files[0].source == cover
    assert not (tmp_path / "out").exists()


def test_adapter_rejects_media_outside_the_platform(tmp_path):
    root = tmp_path / "GBA"
    root.mkdir()
    rom = root / "a.gba"
    rom.write_bytes(b"rom")
    cover = tmp_path / "external.png"
    cover.write_bytes(b"image")
    library = Library(format="pegasus", systems=[System(id="gba", name="GBA", metadata={"source_root": str(root)},
                      games=[Game(name="A", roms=[Rom(path=rom)], media=Media(box_front=cover))])])
    with pytest.raises(ValidationError, match="平台目录外"):
        SaveDeckAdapter(SystemRegistry.load()).render_library(library, tmp_path / "out", ExportOptions(rom_mode="none"))


def test_multiple_existing_entries_use_rom_names_sort_and_uuid4(tmp_path):
    source = tmp_path / "GBA"
    source.mkdir()
    roms = []
    for filename in ("原版.zip", "改版.zip"):
        path = source / filename
        path.write_bytes(b"rom")
        roms.append(Rom(path=path))
    roms.append(Rom(path=source / "缺失版本.zip"))
    cover = source / "cover.png"
    cover.write_bytes(b"cover")
    library = Library(format="pegasus", systems=[System(id="gba", name="GBA", metadata={"source_root": str(source)},
                      games=[Game(name="游戏", roms=roms, media=Media(box_front=cover))])])
    intent = SaveDeckAdapter(SystemRegistry.load()).render_library(library, tmp_path / "out", ExportOptions(rom_mode="none"))
    games = parse_document(intent.texts[0].content.encode())["games"]
    assert [entry["name"] for entry in games] == ["原版", "改版"]
    assert [entry["sort"] for entry in games] == ["000001", "000002"]
    assert all(UUID(entry["id"]).version == 4 for entry in games)
    assert games[0]["id"] != games[1]["id"]
    assert [entry["cover"] for entry in games] == ["media/原版/cover.png", "media/改版/cover.png"]
    assert [request.destination.as_posix() for request in intent.files] == ["gba/media/原版/cover.png", "gba/media/改版/cover.png"]
    assert [item.code for item in intent.diagnostics] == ["missing-rom"]


def test_official_profile_preserves_description_and_recovers_broken_explicit_media(tmp_path):
    from retrolibx.adapters.pegasus.adapter import PegasusAdapter
    source = tmp_path / "GBA"
    (source / "media/游戏").mkdir(parents=True)
    (source / "game.gba").write_bytes(b"rom")
    (source / "media/游戏/boxfront.png").write_bytes(b"valid alternate")
    (source / "metadata.pegasus.txt").write_text(
        "collection: GBA\nextensions: gba\n\ngame: 游戏\nfile: game.gba\n"
        "developer: 游戏 汉化版\ndescription: 原简介\nassets.boxfront: media/错误/boxfront.png\n", encoding="utf-8")
    profile = Path(__file__).resolve().parents[2] / "src/retrolibx/profiles/pegasus-g-savedeck.json"
    library = PegasusAdapter(SystemRegistry.load()).import_library(source, ImportOptions(source_profile=profile)).library
    assert library.systems[0].games[0].description == "原简介"
    intent = SaveDeckAdapter(SystemRegistry.load()).render_library(library, tmp_path / "out", ExportOptions(rom_mode="none"))
    data = parse_document(intent.texts[0].content.encode())
    assert data["games"][0]["cover"] == "media/游戏/cover.png"
    assert data["games"][0]["x_pegasus_developer"] == "游戏 汉化版"
    assert data["games"][0]["x_pegasus_assets_box_front"] == "media/错误/boxfront.png"
    assert len(intent.files) == 1
    assert intent.files[0].source == source / "media/游戏/boxfront.png"
    assert any(item.code == "repaired-media-reference" for item in library.diagnostics)


def test_official_aliases_reject_conflicting_single_values():
    from retrolibx.adapters.pegasus.savedeck_policy import canonical_fields
    with pytest.raises(ParseError, match="冲突"):
        canonical_fields({"launch": ["one"], "command": ["two"]})


def test_one_existing_version_uses_original_game_name_and_excludes_missing_media(tmp_path):
    source = tmp_path / "GBA"
    source.mkdir()
    (source / "present.zip").write_bytes(b"rom")
    cover = source / "cover.png"
    cover.write_bytes(b"cover")
    library = Library(format="pegasus", systems=[System(
        id="gba", name="GBA", metadata={"source_root": str(source)},
        games=[Game(name="游戏", roms=[Rom(path=source / "missing.zip"), Rom(path=source / "present.zip")],
                    media=Media(box_front=cover))])])
    intent = SaveDeckAdapter(SystemRegistry.load()).render_library(library, tmp_path / "out", ExportOptions(rom_mode="none"))
    games = parse_document(intent.texts[0].content.encode())["games"]
    assert [(game["file"], game["name"], game["sort"]) for game in games] == [("present.zip", "游戏", "000001")]
    assert len(intent.files) == 1
    assert intent.files[0].destination.as_posix().endswith("media/游戏/cover.png")
    assert [item.code for item in intent.diagnostics] == ["missing-rom"]


def test_pegasus_game_launch_overrides_are_preserved_and_defaults_inherited(tmp_path):
    from retrolibx.application.service import ConversionService

    source = tmp_path / "roms"
    platform = source / "GBA"
    platform.mkdir(parents=True)
    for filename in ("default.gba", "custom.gba"):
        (platform / filename).write_bytes(b"rom")
    (platform / "metadata.pegasus.txt").write_text(
        'collection: GBA\nlaunch: am start\n  -e LIBRETRO mgba.so -e ROM "{file.path}"\n'
        'game: 默认\nfile: default.gba\n'
        'game: 专属\nfile: custom.gba\ncommand: am start\n  -e LIBRETRO gpsp.so -e ROM "{file.path}"\n', encoding="utf-8")
    target = tmp_path / "out"
    config = target / "GBA/savedeck.toml"
    config.parent.mkdir(parents=True)
    config.write_text(render_document({"platform": "GBA", "games": [{"name": "失效旧条目", "file": "gone.gba"}]}), encoding="utf-8")
    ConversionService().convert(source, target, "savedeck", source_format="pegasus", export_options=ExportOptions(rom_mode="none"))
    data = parse_document(config.read_bytes())
    assert data["launch"] == 'am start -e LIBRETRO mgba.so -e ROM "{file.path}"'
    assert [game["file"] for game in data["games"]] == ["default.gba", "custom.gba"]
    assert "launch" not in data["games"][0]
    assert data["games"][1]["launch"] == 'am start -e LIBRETRO gpsp.so -e ROM "{file.path}"'
