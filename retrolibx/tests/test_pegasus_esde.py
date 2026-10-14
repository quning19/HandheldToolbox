import hashlib
from pathlib import Path

import pytest
from lxml import etree

from retrolibx.adapters.esde.adapter import ESDEAdapter
from retrolibx.adapters.esde.merge import merge_gamelist, merge_gamelists
from retrolibx.adapters.pegasus.adapter import PegasusAdapter
from retrolibx.adapters.pegasus.metadata import parse_metadata
from retrolibx.core.executor import PlanExecutor
from retrolibx.core.models import Game, Library, Media, Rom, System
from retrolibx.core.operations import ExportIntent, TextRequest
from retrolibx.core.options import ExportOptions, ImportOptions, RomMode
from retrolibx.core.planner import ConversionPlanner
from retrolibx.errors import FileOperationError, ParseError, ValidationError
from retrolibx.registry import SystemRegistry


def test_explicit_legacy_rom_root_preserves_user_fields_and_remaps_path():
    old = b'<gameList><game><path>/storage/card/Roms/psx/game.chd</path><name>User name</name><favorite>true</favorite></game></gameList>'
    incoming = '<gameList><game><path>./game.chd</path><name>Imported name</name><desc>New description</desc></game></gameList>'
    with pytest.raises(ValidationError, match="outside system root"):
        merge_gamelist(incoming, old, "/storage/card/Roms/PS1")
    result = etree.fromstring(merge_gamelist(incoming, old, "/storage/card/Roms/PS1", ["/storage/card/Roms/psx"]).encode())
    assert len(result.findall("game")) == 1
    assert result.findtext("game/path") == "./game.chd"
    assert result.findtext("game/name") == "User name"
    assert result.findtext("game/favorite") == "true"
    assert result.findtext("game/desc") == "New description"


def test_legacy_list_id_reuses_user_data_without_claiming_new_target_exists(tmp_path):
    donor = tmp_path / "gamelists/famicom/gamelist.xml"
    donor.parent.mkdir(parents=True)
    original = b'<gameList><game><path>./game.zip</path><name>User</name><favorite>true</favorite></game></gameList>'
    donor.write_bytes(original)
    request = TextRequest(destination="gamelists/nes/gamelist.xml", content='<gameList><game><path>./game.zip</path><name>Imported</name></game></gameList>')
    intent = ExportIntent(texts=[request])
    merge_gamelists(intent, tmp_path, {"nes": "/storage/card/Roms/FC"}, source_systems={"nes": "famicom"})
    output = etree.fromstring(intent.texts[0].content.encode())
    assert output.findtext("game/name") == "User" and output.findtext("game/favorite") == "true"
    assert intent.texts[0].expected_sha256 == ""
    assert donor.read_bytes() == original and not (tmp_path / "gamelists/nes/gamelist.xml").exists()


def test_blank_lines_comments_files_and_flowing_text() -> None:
    text = """collection: GBA
launch: first
  second

# comment
game: A
files:
  dir/a.zip
  dir/b.zip

description: paragraph
  continuation
x-custom: keep
game: B
file: b.zip
"""
    records = parse_metadata(text)
    assert len(records) == 3
    assert records[0]["launch"] == ["first\nsecond"]
    assert records[1]["files"] == ["", "dir/a.zip", "dir/b.zip"]
    assert records[1]["description"] == ["paragraph\ncontinuation"]
    with pytest.raises(ParseError):
        parse_metadata("not metadata")


def test_shared_media_and_nested_names(tmp_path: Path) -> None:
    root = tmp_path / "GBA"
    for relative in ["版本A/game.zip", "版本B/game.zip", "media/A/boxfront.png"]:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"data")
    (root / "metadata.pegasus.txt").write_text(
        "collection: GBA\ngame: A\nfiles:\n  版本A/game.zip\n  版本B/game.zip\nx-custom: keep\n",
        encoding="utf-8",
    )
    registry = SystemRegistry.load()
    pegasus = PegasusAdapter(registry)
    library = pegasus.import_library(root, ImportOptions(
        source_profile=Path(__file__).parents[1] / "src/retrolibx/profiles/pegasus-g.json"
    )).library
    assert len(library.systems[0].games[0].roms) == 2
    intent = ESDEAdapter(registry).render_library(
        library, tmp_path / "out", ExportOptions(rom_mode=RomMode.NONE)
    )
    xml = etree.fromstring(intent.texts[0].content.encode())
    assert [g.findtext("path") for g in xml.findall("game")] == [
        "./版本A/game.zip",
        "./版本B/game.zip",
    ]
    assert {str(f.destination) for f in intent.files} == {
        "downloaded_media/gba/covers/版本A/game.png",
        "downloaded_media/gba/covers/版本B/game.png",
        "downloaded_media/gba/covers/版本A.png",
        "downloaded_media/gba/covers/版本B.png",
    }
    assert len(intent.media_bindings) == 1
    roundtrip = pegasus.render_library(library, tmp_path / "pegasus", ExportOptions())
    assert "x-custom: keep" in roundtrip.texts[0].content
    assert "file: 版本A/game.zip" in roundtrip.texts[0].content


def test_folder_cover_prefers_direct_rom_then_stable_path_and_skips_missing_rom(tmp_path):
    games = []
    for relative, cover_name, exists in [
        ("Set/deep/A.gba", "nested.webp", True),
        ("Set/Z.gba", "last.png", True),
        ("Set/A.gba", "first.png", True),
        ("Missing/game.gba", "missing.png", False),
    ]:
        rom = tmp_path / relative
        if exists:
            rom.parent.mkdir(parents=True, exist_ok=True)
            rom.write_bytes(b"rom")
        cover = tmp_path / cover_name
        cover.write_bytes(b"cover")
        games.append(Game(
            name=relative,
            roms=[Rom(path=rom, metadata={"relative_path": relative})],
            media=Media(box_front=cover),
        ))
    intent = ESDEAdapter(SystemRegistry.load()).render_library(
        Library(format="pegasus", systems=[System(id="gba", name="GBA", games=games)]),
        tmp_path / "output", ExportOptions(rom_mode=RomMode.NONE),
    )
    sources = {str(request.destination): request.source for request in intent.files}
    assert sources["downloaded_media/gba/covers/Set.png"] == tmp_path / "first.png"
    assert sources["downloaded_media/gba/covers/Set/deep.webp"] == tmp_path / "nested.webp"
    assert "downloaded_media/gba/covers/Missing.png" not in sources
    assert len(intent.media_bindings) == 4


def test_folder_cover_keeps_dots_and_unicode_and_does_not_create_extra_games(tmp_path):
    relative = "系列.v1/合集/game.gba"
    rom = tmp_path / relative
    rom.parent.mkdir(parents=True)
    rom.write_bytes(b"rom")
    cover = tmp_path / "cover.JPEG"
    cover.write_bytes(b"cover")
    intent = ESDEAdapter(SystemRegistry.load()).render_library(
        Library(format="pegasus", systems=[System(
            id="gba", name="GBA", games=[Game(
                name="Game", roms=[Rom(path=rom, metadata={"relative_path": relative})],
                media=Media(box_front=cover),
            )],
        )]), tmp_path / "output", ExportOptions(rom_mode=RomMode.NONE),
    )
    assert {str(request.destination) for request in intent.files} == {
        "downloaded_media/gba/covers/系列.v1.jpg",
        "downloaded_media/gba/covers/系列.v1/合集.jpg",
        "downloaded_media/gba/covers/系列.v1/合集/game.jpg",
    }
    xml = etree.fromstring(intent.texts[0].content.encode())
    assert len(xml.findall("game")) == 1
    assert xml.findtext("game/path") == "./系列.v1/合集/game.gba"
    assert xml.find("game/image") is None


def test_folder_cover_collision_preserves_game_media(tmp_path):
    games = []
    for relative, cover_name in [("Set.zip", "root.png"), ("Set/game.gba", "child.png")]:
        rom = tmp_path / relative
        rom.parent.mkdir(parents=True, exist_ok=True)
        rom.write_bytes(b"rom")
        cover = tmp_path / cover_name
        cover.write_bytes(b"cover")
        games.append(Game(
            name=relative, roms=[Rom(path=rom, metadata={"relative_path": relative})],
            media=Media(box_front=cover),
        ))
    intent = ESDEAdapter(SystemRegistry.load()).render_library(
        Library(format="pegasus", systems=[System(id="gba", name="GBA", games=games)]),
        tmp_path / "output", ExportOptions(rom_mode=RomMode.NONE),
    )
    assert len(intent.files) == 2
    assert next(request.source for request in intent.files
                if str(request.destination) == "downloaded_media/gba/covers/Set.png") == tmp_path / "root.png"
    assert [issue.code for issue in intent.diagnostics] == ["folder-cover-collision"]


def test_encoding_and_platform_boundaries(tmp_path: Path) -> None:
    root = tmp_path / "Roms"
    for folder in [root / "GBA", root / "GBA/Child"]:
        folder.mkdir(parents=True)
        (folder / "a.zip").write_bytes(b"rom")
        (folder / "metadata.pegasus.txt").write_bytes(
            "collection: GBA\ngame: 中文\nfile: a.zip\n".encode("gbk")
        )
    adapter = PegasusAdapter(SystemRegistry.load())
    with pytest.raises(ParseError):
        adapter.import_library(root, ImportOptions(platforms=["GBA"]))
    library = adapter.import_library(
        root, ImportOptions(platforms=["GBA"], metadata_encoding="gbk")
    ).library
    assert library.game_count == 1
    with pytest.raises(ParseError):
        adapter.import_library(root, ImportOptions(platforms=["unknown"]))
    (root / "GBA/metadata.pegasus.txt").write_text(
        "collection: GBA\ngame: bad\nfile: ../other.zip\n", encoding="utf-8"
    )
    with pytest.raises(ParseError):
        adapter.import_library(root, ImportOptions(platforms=["GBA"]))


def test_media_collision_rejected(tmp_path: Path) -> None:
    media = tmp_path / "box.png"
    media.write_bytes(b"png")
    library = Library(
        format="pegasus",
        systems=[
            System(
                id="gba",
                name="GBA",
                games=[
                    Game(
                        name="A",
                        roms=[Rom(path=tmp_path / "a.zip"), Rom(path=tmp_path / "a.gba")],
                        media=Media(box_front=media),
                    )
                ],
            )
        ],
    )
    with pytest.raises(ValidationError):
        ESDEAdapter(SystemRegistry.load()).render_library(
            library, tmp_path / "out", ExportOptions()
        )


def test_merge_preserves_all_user_fields_and_extra_game() -> None:
    old = b"""<gameList><game><path>/storage/Roms/GBA/a.zip</path><name>User</name>
<favorite>true</favorite><playtime>99</playtime><altemulator>custom</altemulator>
<desc>User description</desc></game><game><path>./extra.zip</path></game></gameList>"""
    new = "<gameList><game><path>./a.zip</path><name>New</name><desc>New description</desc><sortname>1</sortname></game></gameList>"
    root = etree.fromstring(merge_gamelist(new, old, "/storage/Roms/GBA").encode())
    assert len(root.findall("game")) == 2
    assert root.findtext("game/name") == "User"
    assert root.findtext("game/desc") == "User description"
    assert root.findtext("game/playtime") == "99"
    assert root.findtext("game/altemulator") == "custom"
    assert root.findtext("game/sortname") == "1"
    for invalid in [b"<broken>", b"<gameList><game/></gameList>", b"<!DOCTYPE x><gameList/>"]:
        with pytest.raises(ValidationError):
            merge_gamelist(new, invalid, "/storage/Roms/GBA")


def test_configuration_baseline_and_backup(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    xml = target / "gamelist.xml"
    xml.write_bytes(b"old")
    intent = ExportIntent(
        texts=[
            TextRequest(
                destination="gamelist.xml",
                content="new",
                expected_sha256=hashlib.sha256(b"old").hexdigest(),
                backup=True,
            )
        ]
    )
    plan = ConversionPlanner().plan(
        intent,
        source_root=tmp_path / "source",
        target_root=target,
        source_format="a",
        target_format="b",
        options=ExportOptions(),
    )
    xml.write_bytes(b"changed")
    with pytest.raises(FileOperationError):
        PlanExecutor().execute(plan)
    assert xml.read_bytes() == b"changed"
    xml.write_bytes(b"old")
    PlanExecutor().execute(plan)
    assert xml.read_bytes() == b"new"
    assert target.joinpath("gamelist.xml.frontendtrans.bak").read_bytes() == b"old"
    PlanExecutor().execute(plan)
    assert target.joinpath("gamelist.xml.frontendtrans.bak").read_bytes() == b"old"


def test_pegasus_preserves_uninterpreted_source_fields(tmp_path: Path) -> None:
    game = Game(
        name="A",
        roms=[Rom(path=tmp_path / "a.zip")],
        source_metadata={
            "pegasus_fields": {"release": ["unsupported date"], "x-extra": ["retained"]}
        },
    )
    library = Library(format="pegasus", systems=[System(id="gba", name="GBA", games=[game])])
    output = PegasusAdapter(SystemRegistry.load()).render_library(
        library, tmp_path / "out", ExportOptions()
    )
    assert "release: unsupported date" in output.texts[0].content
    assert "x-extra: retained" in output.texts[0].content
