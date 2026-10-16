"""ES-DE ownership transfer regressions; execution requires explicit approval."""
from pathlib import Path
import base64
import codecs
import hashlib
import json
from unittest.mock import patch

import pytest

from retrolibx.adapters.esde.adapter import ESDEAdapter
from retrolibx.adapters.pegasus.adapter import PegasusAdapter
from retrolibx.application.service import ConversionService
from library_converter.handheld import HandheldConfig, build_handheld
from retrolibx.core.models import Game, Library, Media, Rom, System
from retrolibx.core.operations import TransferFile, WriteSourceMetadata, MigrateSourceMedia
from retrolibx.core.executor import PlanExecutor
from retrolibx.adapters.pegasus.metadata import patch_asset_references
from retrolibx.core.options import ConflictPolicy, ExportOptions, ImportOptions, RomMode
from retrolibx.errors import ValidationError, FileOperationError
from retrolibx.registry import SystemRegistry

PROFILE = Path(__file__).parents[2] / "src/retrolibx/profiles/pegasus-g.json"


def source_library(tmp_path: Path) -> Path:
    source = tmp_path / "Roms/GBA"
    source.joinpath("nested").mkdir(parents=True)
    source.joinpath("nested/game.zip").write_bytes(b"rom")
    source.joinpath("media/Game").mkdir(parents=True)
    source.joinpath("media/Game/boxFront.jpeg").write_bytes(b"cover")
    source.joinpath("metadata.pegasus.txt").write_bytes((
        "collection: GBA\r\nlaunch: original {file.path}\r\n"
        "game: Game\r\nfile: nested/game.zip\r\nx-custom: retained\r\n"
    ).encode("utf-8"))
    return source


def test_three_media_roles_preserve_paths_and_ignore_other_assets(tmp_path: Path) -> None:
    source = source_library(tmp_path)
    for name in ["wheel.webp", "video.mp4", "box_back.png", "screenshot.jpg",
                 "titlescreen.png", "background.webp", "disc.png"]:
        source.joinpath("media/Game", name).write_bytes(b"unchanged-media")
    metadata = source / "metadata.pegasus.txt"
    extra_assets = {
        "box_back": "box_back.png", "screenshot": "screenshot.jpg",
        "titlescreen": "titlescreen.png", "background": "background.webp",
        "cartridge": "disc.png",
    }
    metadata.write_text(
        metadata.read_text(encoding="utf-8")
        + "".join(f"assets.{role}: media/Game/{name}\n" for role, name in extra_assets.items()),
        encoding="utf-8",
    )
    registry = SystemRegistry.load()
    library = PegasusAdapter(registry).import_library(
        source, ImportOptions(source_profile=PROFILE)
    ).library
    intent = ESDEAdapter(registry).render_library(
        library, tmp_path / "out", ExportOptions(rom_mode=RomMode.NONE)
    )
    assert {file.destination.as_posix() for file in intent.files} == {
        "downloaded_media/gba/covers/nested.jpg",
        "downloaded_media/gba/covers/nested/game.jpg",
        "downloaded_media/gba/marquees/nested/game.webp",
        "downloaded_media/gba/videos/nested/game.mp4",
    }
    assert len(intent.media_bindings) == 3
    assert not any(d.code == "missing-media" for d in library.diagnostics)
    assert intent.files[0].source.read_bytes() == b"cover"
    assert not (tmp_path / "out").exists()


def test_pegasus_g_only_looks_for_three_media_roles(tmp_path: Path) -> None:
    source = source_library(tmp_path)
    for name in ["logo.png", "video.mp4"]:
        source.joinpath("media/Game", name).write_bytes(b"media")
    library = PegasusAdapter(SystemRegistry.load()).import_library(
        source, ImportOptions(source_profile=PROFILE)
    ).library
    game = library.systems[0].games[0]
    assert game.media.box_front == source / "media/Game/boxFront.jpeg"
    assert game.media.logo == source / "media/Game/logo.png"
    assert game.media.video == source / "media/Game/video.mp4"
    assert not any(d.code == "missing-media" for d in library.diagnostics)


def test_invalid_explicit_reference_falls_back_but_ambiguous_media_does_not(tmp_path: Path) -> None:
    source = source_library(tmp_path)
    meta = source / "metadata.pegasus.txt"
    meta.write_text(meta.read_text(encoding="utf-8") + "assets.box_front: missing.png\n", encoding="utf-8")
    adapter = PegasusAdapter(SystemRegistry.load())
    options = ImportOptions(source_profile=PROFILE)
    repaired = adapter.import_library(source, options)
    assert repaired.library.systems[0].games[0].media.box_front == source / "media/Game/boxFront.jpeg"
    assert any(d.code == "repaired-media-reference" for d in repaired.diagnostics)
    source.joinpath("media/Game/box_front.webp").write_bytes(b"other-cover")
    ambiguous = adapter.import_library(source, options)
    assert not ambiguous.library.systems[0].games[0].media.box_front.is_file()
    assert any(d.code == "missing-media" for d in ambiguous.diagnostics)


def test_shared_migration_dry_run_preserves_source_and_plans_original_metadata(tmp_path: Path) -> None:
    source = source_library(tmp_path)
    meta = source / "metadata.pegasus.txt"
    original = meta.read_bytes()
    target = tmp_path / "out"
    service = ConversionService()
    result = service.convert(
        source, target, "es-de", source_format="pegasus",
        import_options=ImportOptions(source_profile=PROFILE),
        export_options=ExportOptions(rom_mode=RomMode.NONE, shared_pegasus=True), dry_run=True,
    )
    media = [op for op in result.plan.operations if isinstance(op, TransferFile) and op.category == "media"]
    updates = [op for op in result.plan.operations if isinstance(op, WriteSourceMetadata)]
    migrations = [op for op in result.plan.operations if isinstance(op, MigrateSourceMedia)]
    assert len(media) == 2 and len(updates) == len(migrations) == 1
    update = updates[0]
    assert update.destination == meta
    desired = base64.b64decode(update.content_base64)
    game_cover = target / "downloaded_media/gba/covers/nested/game.jpg"
    assert desired == original + f"assets.box_front: {game_cover.as_posix()}\r\n".encode()
    assert update.expected_sha256 == hashlib.sha256(original).hexdigest()
    assert migrations[0].targets == sorted([operation.destination for operation in media], key=str)
    assert result.execution is None and not target.exists()
    assert meta.read_bytes() == original


def test_default_conversion_keeps_original_metadata_and_media(tmp_path: Path) -> None:
    source = source_library(tmp_path)
    meta = source / "metadata.pegasus.txt"
    original = meta.read_bytes()
    result = ConversionService().convert(
        source, tmp_path / "out", "es-de", source_format="pegasus",
        import_options=ImportOptions(source_profile=PROFILE),
        export_options=ExportOptions(rom_mode=RomMode.NONE),
    )
    assert meta.read_bytes() == original
    assert source.joinpath("media/Game/boxFront.jpeg").read_bytes() == b"cover"
    assert (tmp_path / "out/downloaded_media/gba/covers/nested.jpg").read_bytes() == b"cover"
    assert not any(isinstance(op, (WriteSourceMetadata, MigrateSourceMedia)) for op in result.plan.operations)


def test_shared_migration_updates_in_place_after_all_rom_copies_and_keeps_mini(tmp_path: Path) -> None:
    source = source_library(tmp_path)
    source.joinpath("nested/second.zip").write_bytes(b"second-rom")
    meta = source / "metadata.pegasus.txt"
    original = meta.read_bytes().replace(b"file: nested/game.zip", b"files:\n  nested/game.zip\n  nested/second.zip")
    meta.write_bytes(original)
    mini = source / "media/Game/mini_boxfront.png"
    mini.write_bytes(b"mini")
    target = tmp_path / "out"
    result = ConversionService().convert(
        source, target, "es-de", source_format="pegasus",
        import_options=ImportOptions(source_profile=PROFILE),
        export_options=ExportOptions(rom_mode=RomMode.NONE, shared_pegasus=True),
    )
    cover = target / "downloaded_media/gba/covers/nested/game.jpg"
    assert cover.read_bytes() == b"cover"
    assert target.joinpath("downloaded_media/gba/covers/nested/second.jpg").read_bytes() == b"cover"
    assert target.joinpath("downloaded_media/gba/covers/nested.jpg").read_bytes() == b"cover"
    assert meta.read_bytes() == original + f"assets.box_front: {cover.as_posix()}\r\n".encode()
    assert not source.joinpath("media/Game/boxFront.jpeg").exists()
    assert mini.read_bytes() == b"mini"
    assert source.joinpath("nested/game.zip").read_bytes() == b"rom"
    assert next(source.glob("metadata.pegasus.txt.frontendtrans.*.bak")).read_bytes() == original
    assert not target.joinpath("pegasus").exists()
    # Re-running the same inspected plan after cleanup must remain safe.
    PlanExecutor().execute(result.plan)
    assert meta.read_bytes() == original + f"assets.box_front: {cover.as_posix()}\r\n".encode()
    regenerated = shared_plan(source, target)
    assert not any(isinstance(op, (WriteSourceMetadata, MigrateSourceMedia)) for op in regenerated.operations)


def test_shared_migration_rejects_renaming_and_rom_moves(tmp_path: Path) -> None:
    source = source_library(tmp_path)
    service = ConversionService()
    with pytest.raises(ValidationError, match="stable filenames"):
        service.convert(
            source, tmp_path / "other", "es-de", source_format="pegasus",
            export_options=ExportOptions(rom_mode=RomMode.NONE, shared_pegasus=True, conflict=ConflictPolicy.RENAME), dry_run=True,
        )
    with pytest.raises(ValidationError, match="ROM mode none"):
        service.convert(source, tmp_path / "other", "es-de", source_format="pegasus",
                        export_options=ExportOptions(shared_pegasus=True), dry_run=True)


def shared_plan(source: Path, target: Path):
    return ConversionService().convert(
        source, target, "es-de", source_format="pegasus",
        import_options=ImportOptions(source_profile=PROFILE),
        export_options=ExportOptions(rom_mode=RomMode.NONE, shared_pegasus=True), dry_run=True,
    ).plan


def test_changed_metadata_or_differing_target_stops_before_source_mutations(tmp_path: Path) -> None:
    source = source_library(tmp_path)
    meta = source / "metadata.pegasus.txt"
    original = meta.read_bytes()
    target = tmp_path / "out"
    plan = shared_plan(source, target)
    meta.write_bytes(original + b"# edited after planning\n")
    with pytest.raises(FileOperationError, match="metadata changed"):
        PlanExecutor().execute(plan)
    assert not target.exists()
    meta.write_bytes(original)
    cover = target / "downloaded_media/gba/covers/nested/game.jpg"
    cover.parent.mkdir(parents=True)
    cover.write_bytes(b"different")
    plan = shared_plan(source, target)
    with pytest.raises(FileOperationError, match="differs"):
        PlanExecutor().execute(plan)
    assert meta.read_bytes() == original
    assert source.joinpath("media/Game/boxFront.jpeg").read_bytes() == b"cover"
    assert cover.read_bytes() == b"different"


def test_failed_copy_never_publishes_source_metadata_or_cleans_sources(tmp_path: Path) -> None:
    source = source_library(tmp_path)
    meta = source / "metadata.pegasus.txt"
    original = meta.read_bytes()
    plan = shared_plan(source, tmp_path / "out")
    with patch.object(PlanExecutor, "_transfer", side_effect=FileOperationError("copy failed")):
        with pytest.raises(FileOperationError, match="copy failed"):
            PlanExecutor().execute(plan)
    assert meta.read_bytes() == original
    assert source.joinpath("media/Game/boxFront.jpeg").read_bytes() == b"cover"


@pytest.mark.parametrize("encoding,prefix", [("utf-8-sig", codecs.BOM_UTF8), ("gbk", b"")])
def test_asset_patch_preserves_encoding_comments_crlf_and_non_asset_fields(encoding: str, prefix: bytes) -> None:
    text = (
        "# 原始注释\r\ncollection: GBA\r\nlaunch: original {file.path}\r\n\r\n"
        "game: 游戏\r\nfile: nested/game.zip\r\nsort-by: 007\r\n"
        "developer: 游戏 v2\r\ndescription: 第一段\r\n  第二段\r\n"
        "Assets.boxFront :  media/游戏/boxfront.png\r\n# 保留注释\r\n"
    )
    raw = text.encode(encoding)
    expected = raw.replace("media/游戏/boxfront.png".encode("utf-8" if prefix else encoding), b"/storage/emulated/0/ES-DE/downloaded_media/gba/covers/game.png")
    patched = patch_asset_references(raw, {0: {"box_front": "/storage/emulated/0/ES-DE/downloaded_media/gba/covers/game.png"}}, encoding)
    assert patched == expected
    assert patched.startswith(prefix)


def test_other_asset_reference_retains_shared_source_file(tmp_path: Path) -> None:
    source = source_library(tmp_path)
    meta = source / "metadata.pegasus.txt"
    meta.write_bytes(meta.read_bytes() + b"assets.x-custom: media/Game/boxFront.jpeg\n")
    result = ConversionService().convert(
        source, tmp_path / "out", "es-de", source_format="pegasus",
        import_options=ImportOptions(source_profile=PROFILE),
        export_options=ExportOptions(rom_mode=RomMode.NONE, shared_pegasus=True),
    )
    assert source.joinpath("media/Game/boxFront.jpeg").read_bytes() == b"cover"
    assert b"assets.x-custom: media/Game/boxFront.jpeg\n" in meta.read_bytes()
    assert any(d.code == "shared-source-retained" for d in result.plan.diagnostics)


def test_case_alias_media_collision_is_rejected(tmp_path: Path) -> None:
    source = source_library(tmp_path)
    cover = source / "media/Game/boxFront.jpeg"
    library = Library(format="pegasus", systems=[System(id="gba", name="GBA", games=[Game(
        name="Game", roms=[Rom(path=source / "a.zip"), Rom(path=source / "A.gba")],
        media=Media(box_front=cover),
    )])])
    with pytest.raises(ValidationError, match="collision"):
        ESDEAdapter(SystemRegistry.load()).render_library(library, tmp_path / "out", ExportOptions())


@pytest.mark.parametrize("shared", [False, True])
def test_android_shared_migration_is_opt_in_and_build_does_not_change_source(tmp_path: Path, shared: bool) -> None:
    source = source_library(tmp_path)
    original = source.joinpath("metadata.pegasus.txt").read_bytes()
    config = HandheldConfig(
        source_root=source.parent, device_rom_root="/storage/emulated/0/Test/Roms",
        esde_root="/storage/emulated/0/Test/ES-DE", target_empty=True, shared_pegasus=shared,
    )
    output = tmp_path / "task"
    summary = build_handheld(config, ["GBA"], output)
    assert summary["media_targets"] == 2
    assert summary["source_metadata_updates"] == int(shared)
    assert not output.joinpath("files/pegasus").exists()
    script = output.joinpath("apply.sh").read_text(encoding="utf-8")
    assert "/covers/nested.jpg" in script
    if shared:
        encoded = output / "files/source-metadata/GBA/metadata.pegasus.txt.b64"
        desired = base64.b64decode(encoded.read_text())
        assert desired == original + b"assets.box_front: /storage/emulated/0/Test/ES-DE/downloaded_media/gba/covers/nested/game.jpg\r\n"
        assert summary["source_media_cleanup"] == 1
        assert "cp -n -- " in script and "sha256sum" not in script
        assert "publish_source_metadata" not in script and "remove_shared_source" not in script
        publication = json.loads((output / "publication.json").read_text(encoding="utf-8"))
        assert any(write["category"] == "source-metadata" for write in publication["writes"])
        assert len(publication["cleanup"]) == 1
    else:
        assert summary["source_media_cleanup"] == 0
        assert "publish_source_metadata" not in script and "remove_shared_source" not in script
    assert source.joinpath("metadata.pegasus.txt").read_bytes() == original
