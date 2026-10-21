"""SaveDeck publishing uses temporary sources and simulated ADB only."""

import hashlib
from pathlib import Path

import pytest

from frontend_devices.discovery import Device
from frontend_platforms.user_catalog import default_definitions
from library_converter.savedeck import convert_savedeck, scan_savedeck
from retrolibx.adapters.savedeck.document import parse_document, render_document
from retrolibx.errors import RetroLibXError, ValidationError


def setup_source(tmp_path):
    source = tmp_path / "roms"
    platform = source / "GBA"
    platform.mkdir(parents=True)
    (platform / "游戏.gba").write_bytes(b"original rom")
    (platform / "cover.png").write_bytes(b"original cover")
    (platform / "metadata.pegasus.txt").write_text(
        'collection: GBA\nlaunch: am start -n test/.Main -e ROM {file.path}\n\n'
        'game: 游戏\nfile: 游戏.gba\nassets.box_front: cover.png\ndescription: 原简介\n', encoding="utf-8")
    return source, platform


def scan(tmp_path, source):
    return scan_savedeck(tmp_path / "work", default_definitions(), str(source), None,
                         lambda: False, lambda *_: None, lambda _: None)


def publish(tmp_path, session, full=False):
    return convert_savedeck(session, ["GBA"], False, full, tmp_path / "work", lambda: False, lambda *_: None)


def test_local_export_adds_official_media_and_preserves_original_rom_media_and_pegasus(tmp_path):
    source, platform = setup_source(tmp_path)
    originals = {p.name: p.read_bytes() for p in platform.iterdir()}
    session = scan(tmp_path, source)
    assert session.platforms["GBA"].error == ""
    result = publish(tmp_path, session)
    assert result["roms"] == 1
    data = parse_document((platform / "savedeck.toml").read_bytes())
    assert data["games"][0]["file"] == "游戏.gba"
    assert data["games"][0]["cover"] == "media/游戏/cover.png"
    assert data["launch"].startswith("am start")
    assert all((platform / name).read_bytes() == raw for name, raw in originals.items())
    assert set(p.name for p in platform.iterdir()) == set(originals) | {"savedeck.toml", "media"}
    assert (platform / "media/游戏/cover.png").read_bytes() == originals["cover.png"]
    assert not (source / ".retrolibx").exists()
    assert (Path(result["export"]) / "GBA/savedeck.toml").is_file()


def test_repeat_export_preserves_user_fields_and_uuid_and_backs_up(tmp_path):
    source, platform = setup_source(tmp_path)
    publish(tmp_path, scan(tmp_path, source))
    path = platform / "savedeck.toml"
    data = parse_document(path.read_bytes())
    identifier = data["games"][0]["id"]
    data["games"][0].update(name="用户名称", custom="keep", sort="003")
    path.write_text(render_document(data), encoding="utf-8")
    original = path.read_bytes()
    publish(tmp_path, scan(tmp_path, source))
    assert parse_document(path.read_bytes())["games"][0] == dict(data["games"][0], sort="000001")
    publish(tmp_path, scan(tmp_path, source), full=True)
    updated = parse_document(path.read_bytes())
    assert updated["games"][0]["name"] == "游戏"
    assert updated["games"][0]["id"] == identifier
    assert updated["games"][0]["custom"] == "keep"
    assert updated["games"][0]["sort"] == "000001"
    assert path.with_name(path.name + ".frontendtrans.bak").read_bytes() == original


@pytest.mark.parametrize("filename", ["metadata.pegasus.txt", "savedeck.toml"])
def test_changes_after_loading_block_publication(tmp_path, filename):
    source, platform = setup_source(tmp_path)
    publish(tmp_path, scan(tmp_path, source))
    session = scan(tmp_path, source)
    path = platform / filename
    path.write_bytes(path.read_bytes() + b"\n# changed\n")
    changed = path.read_bytes()
    with pytest.raises(RetroLibXError):
        publish(tmp_path, session, full=True)
    assert path.read_bytes() == changed


def test_new_registered_rom_is_added_and_unregistered_rom_is_not_imported(tmp_path):
    source, platform = setup_source(tmp_path)
    publish(tmp_path, scan(tmp_path, source))
    config = platform / "savedeck.toml"
    identifier = parse_document(config.read_bytes())["games"][0]["id"]
    (platform / "新增.gba").write_bytes(b"new rom")
    (platform / "未登记.gba").write_bytes(b"unregistered rom")
    metadata = platform / "metadata.pegasus.txt"
    metadata.write_text(metadata.read_text(encoding="utf-8") + "\ngame: 新增游戏\nfile: 新增.gba\n", encoding="utf-8")
    session = scan(tmp_path, source)
    assert session.platforms["GBA"].roms == 2
    assert session.platforms["GBA"].existing == 1
    result = publish(tmp_path, session)
    games = parse_document(config.read_bytes())["games"]
    assert [game["file"] for game in games] == ["新增.gba", "游戏.gba"]
    assert games[1]["id"] == identifier
    assert games[0]["id"] != identifier
    assert result["roms"] == 1
    assert (platform / "未登记.gba").read_bytes() == b"unregistered rom"


def test_version_addition_and_deletion_update_names_without_changing_surviving_id(tmp_path):
    source = tmp_path / "roms"
    platform = source / "GBA"
    platform.mkdir(parents=True)
    (platform / "主版.gba").write_bytes(b"first version")
    (platform / "metadata.pegasus.txt").write_text(
        "collection: GBA\ngame: 原游戏名\nfiles:\n  主版.gba\n  改版.gba\n", encoding="utf-8")
    publish(tmp_path, scan(tmp_path, source))
    config = platform / "savedeck.toml"
    first = parse_document(config.read_bytes())["games"][0]
    assert first["name"] == "原游戏名"
    (platform / "改版.gba").write_bytes(b"second version")
    publish(tmp_path, scan(tmp_path, source))
    added = parse_document(config.read_bytes())["games"]
    assert [game["name"] for game in added] == ["原游戏名", "原游戏名 · 改版"]
    publish(tmp_path, scan(tmp_path, source), full=True)
    updated = parse_document(config.read_bytes())["games"]
    assert [game["name"] for game in updated] == ["原游戏名 · 主版", "原游戏名 · 改版"]
    assert updated[0]["id"] == first["id"]
    assert updated[1]["id"] == added[1]["id"]
    (platform / "改版.gba").unlink()
    publish(tmp_path, scan(tmp_path, source), full=True)
    remaining = parse_document(config.read_bytes())["games"]
    assert len(remaining) == 1
    assert remaining[0]["name"] == "原游戏名"
    assert remaining[0]["id"] == first["id"]


def test_missing_rom_is_excluded_with_its_media_and_reported(tmp_path):
    source, platform = setup_source(tmp_path)
    (platform / "游戏.gba").unlink()
    session = scan(tmp_path, source)
    assert session.platforms["GBA"].error == ""
    assert session.platforms["GBA"].missing_references == 1
    assert session.platforms["GBA"].roms == 0
    assert session.platforms["GBA"].covers == 0
    result = publish(tmp_path, session)
    assert result["roms"] == 0
    assert result["warnings"]
    assert parse_document((platform / "savedeck.toml").read_bytes())["games"] == []
    assert not (platform / "media").exists()
    assert (platform / "cover.png").read_bytes() == b"original cover"


@pytest.mark.parametrize("full", [False, True])
def test_existing_missing_and_unregistered_entries_are_removed_without_media_cleanup(tmp_path, full):
    source, platform = setup_source(tmp_path)
    publish(tmp_path, scan(tmp_path, source))
    path = platform / "savedeck.toml"
    data = parse_document(path.read_bytes())
    extra = {"name": "自定义游戏", "file": "extra.gba", "custom": "keep", "launch": "custom command"}
    data["games"].extend([extra, {"name": "失效额外条目", "file": "gone.gba"}])
    path.write_text(render_document(data), encoding="utf-8")
    original = path.read_bytes()
    (platform / "extra.gba").write_bytes(b"extra rom")
    (platform / "游戏.gba").unlink()
    result = publish(tmp_path, scan(tmp_path, source), full=full)
    assert parse_document(path.read_bytes())["games"] == []
    assert result["roms"] == 0
    assert result["removed"] == 3
    assert result["warnings"]
    assert path.with_name(path.name + ".frontendtrans.bak").read_bytes() == original
    assert (platform / "media/游戏/cover.png").read_bytes() == b"original cover"


def test_device_path_only_publishes_selected_configs_with_simulated_adb(tmp_path, monkeypatch):
    source, platform = setup_source(tmp_path)
    session = scan(tmp_path, source)
    session.device = Device(Path("unused-adb"), "mock-serial", "mock", "/storage/emulated/0/ES-DE", ())
    session.remote_root = "/storage/1234/roms"
    metadata_hash = hashlib.sha256((platform / "metadata.pegasus.txt").read_bytes()).hexdigest()
    calls = []

    class Publisher:
        def __init__(self, *args, **kwargs):
            pass

        def _digest(self, remote):
            return metadata_hash if remote.endswith("metadata.pegasus.txt") else ""

        def publish_config(self, payload, remote, expected):
            calls.append((payload, remote, expected))

        def copy_media(self, copies, *, overwrite=True):
            assert overwrite is False
            assert copies == [("/storage/1234/roms/GBA/cover.png", "/storage/1234/roms/GBA/media/游戏/cover.png")]

    monkeypatch.setattr("library_converter.savedeck.AdbPublisher", Publisher)
    result = publish(tmp_path, session)
    assert len(calls) == 1
    assert calls[0][1:] == ("/storage/1234/roms/GBA/savedeck.toml", "")
    assert parse_document(calls[0][0].read_bytes())["games"][0]["file"] == "游戏.gba"
    assert result["output"] == session.remote_root
    assert not (platform / "savedeck.toml").exists()


def test_device_changed_baseline_blocks_every_upload(tmp_path, monkeypatch):
    source, _ = setup_source(tmp_path)
    session = scan(tmp_path, source)
    session.device = Device(Path("unused-adb"), "mock-serial", "mock", "/storage/emulated/0/ES-DE", ())
    session.remote_root = "/storage/1234/roms"
    uploads = []

    class Publisher:
        def __init__(self, *args, **kwargs):
            pass

        def _digest(self, remote):
            return "changed"

        def publish_config(self, *args):
            uploads.append(args)

        def copy_media(self, *args):
            uploads.append(args)

    monkeypatch.setattr("library_converter.savedeck.AdbPublisher", Publisher)
    with pytest.raises(ValidationError, match="已变化"):
        publish(tmp_path, session)
    assert uploads == []
