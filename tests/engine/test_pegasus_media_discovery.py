"""Shared source-media rules; run only with explicit user approval."""

from pathlib import Path
from unittest.mock import patch

import pytest

from retrolibx.adapters.pegasus.adapter import PegasusAdapter
from retrolibx.adapters.pegasus.asset_discovery import AssetFiles
from retrolibx.application.service import ConversionService
from retrolibx.core.options import ExportOptions, ImportOptions
from retrolibx.registry import SystemRegistry


@pytest.fixture(params=["pegasus-g", "pegasus-g-savedeck"])
def source(tmp_path, request):
    root = tmp_path / "GBA"
    root.mkdir()
    (root / "rom.gba").write_bytes(b"rom")
    profile = Path(__file__).parents[2] / "src/retrolibx/profiles" / (request.param + ".json")
    return root, profile


def put(root, relative):
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"media")
    return path


def load(source, extra="", **options):
    root, profile = source
    metadata = root / "metadata.pegasus.txt"
    raw = ("collection: GBA\ngame: Game\nfile: rom.gba\n" + extra).encode("utf-8")
    metadata.write_bytes(raw)
    imported = PegasusAdapter(SystemRegistry.load()).import_library(
        root, ImportOptions(source_profile=profile, **options))
    assert metadata.read_bytes() == raw
    return imported.library.systems[0].games[0], imported.diagnostics


@pytest.mark.parametrize("explicit", [False, True])
def test_same_priority_multiple_candidates_select_first_and_report(source, explicit):
    root, _ = source
    first = put(root, "media/Game/box_front.webp")
    second = put(root, "media/Game/boxfront.png")
    put(root, "media/rom/boxfront.jpg")
    game, issues = load(source, "assets.box_front: wrong/boxfront.png\n" if explicit else "")
    assert game.media.box_front == first
    warning = next(issue for issue in issues if issue.code == "multiple-media-candidates")
    assert warning.severity == "warning"
    assert warning.details["priority"] == 2
    assert warning.details["selected"] == str(first)
    assert [item["path"] for item in warning.details["candidates"]] == [str(first), str(second)]
    assert str(first) in warning.message and str(second) in warning.message


@pytest.mark.parametrize("winner", [1, 2, 3, 4])
def test_four_directory_groups_are_priorities_not_a_global_candidate_pool(source, winner):
    root, _ = source
    candidates = {1: "old/boxfront.jpg", 2: "media/Game/boxfront.png",
                  3: "media/rom/boxfront.webp", 4: "other/boxfront.jpeg"}
    expected = None
    for priority, relative in candidates.items():
        if priority >= winner:
            path = put(root, relative)
            if priority == winner:
                expected = path
    put(root, "other/logo.png")
    game, issues = load(source, "assets.box_front: old/boxfront.png\nassets.logo: other/logo.png\n")
    assert game.media.box_front == expected
    decision = next(issue for issue in issues if issue.code == "repaired-media-reference")
    assert decision.details["priority"] == winner
    assert not any(issue.code == "multiple-media-candidates" for issue in issues)


def test_missing_reference_uses_rom_then_other_valid_asset_directory(source):
    root, _ = source
    cover = put(root, "media/rom/boxfront.png")
    logo = put(root, "other/logo.png")
    video = put(root, "other/video.mkv")
    game, _ = load(source, "assets.logo: other/logo.png\n")
    assert game.media.box_front == cover
    assert game.media.logo == logo
    assert game.media.video == video


def test_original_valid_reference_is_preserved_even_with_other_candidates(source):
    root, _ = source
    chosen = put(root, "chosen.png")
    put(root, "media/Game/boxfront.png")
    game, issues = load(source, "assets.box_front: chosen.png\n")
    assert game.media.box_front == chosen
    assert not any(issue.details.get("role") == "box_front" for issue in issues)


def test_empty_asset_field_is_treated_as_no_reference(source):
    root, _ = source
    chosen = put(root, "media/Game/boxfront.png")
    game, _ = load(source, "assets.box_front:\n")
    assert game.media.box_front == chosen


def test_candidate_warning_is_in_the_export_plan_without_source_edits(source, tmp_path):
    root, profile = source
    put(root, "media/Game/box_front.webp")
    put(root, "media/Game/boxfront.png")
    load(source)
    metadata = root / "metadata.pegasus.txt"
    original = metadata.read_bytes()
    target = tmp_path / "out"
    result = ConversionService().convert(
        root, target, "savedeck" if profile.stem.endswith("savedeck") else "es-de",
        source_format="pegasus", import_options=ImportOptions(source_profile=profile),
        export_options=ExportOptions(rom_mode="none"), dry_run=True,
    )
    assert any(issue.code == "multiple-media-candidates" for issue in result.plan.diagnostics)
    assert metadata.read_bytes() == original
    assert not target.exists()


def test_no_thumbnail_no_global_fuzzy_search_and_no_nested_platform_borrowing(source):
    root, _ = source
    put(root, "media/Game/mini_boxfront.png")
    put(root, "unrelated/boxfront.png")
    put(root, "media/Game/Child/boxfront.png")
    put(root, "media/Game/Child/metadata.pegasus.txt")
    # Select the parent explicitly, so the intentionally separate child is not imported.
    game, issues = load(source, platforms=["."])
    assert game.media.box_front is None
    assert any(issue.code == "missing-media" and issue.details["role"] == "box_front" for issue in issues)


def test_no_installed_rom_does_not_start_media_discovery(source):
    root, _ = source
    (root / "rom.gba").unlink()
    put(root, "media/Game/boxfront.png")
    game, issues = load(source)
    assert game.media.box_front is None
    assert not any(issue.code.endswith("media") for issue in issues)


def test_unknown_directory_does_not_choose_a_lower_priority_candidate(source):
    root, _ = source
    put(root, "media/rom/boxfront.png")
    original_children = AssetFiles.children

    def children(files, directory):
        return None if directory == str(root / "media/Game") else original_children(files, directory)

    with patch.object(AssetFiles, "children", children):
        game, issues = load(source)
    assert game.media.box_front is None
    assert any(issue.code == "unknown-media" and issue.details["priority"] == 2 for issue in issues)


def test_incomplete_inventory_does_not_select_media(source):
    root, _ = source
    put(root, "media/Game/boxfront.png")
    with patch.object(AssetFiles, "_read", return_value=None):
        game, issues = load(source)
    assert game.media.box_front is None
    assert any(issue.code == "unknown-media" for issue in issues)


def test_captured_device_absolute_reference_uses_only_its_declared_root(source):
    root, _ = source
    chosen = put(root, "media/Game/selected.png")
    game, _ = load(source, "assets.box_front: /storage/card/Roms/GBA/media/Game/selected.png\n",
                   device_rom_root="/storage/card/Roms/GBA")
    assert game.media.box_front == chosen
