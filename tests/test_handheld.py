import hashlib
import io
import json
import re
import subprocess
import tarfile
from pathlib import Path
from unittest.mock import patch

import pytest
from lxml import etree
from typer.testing import CliRunner

from retrolibx.application.device import AdbReader, _archive_files, capture_device
from retrolibx.application.handheld import HandheldConfig, build_handheld, scan_handheld
from retrolibx.cli import app
from retrolibx.core.android import android_path
from retrolibx.errors import ValidationError


def make_config(tmp_path: Path) -> HandheldConfig:
    root = tmp_path / "source"
    for platform in ["GBA", "GBA vib"]:
        folder = root / platform
        folder.joinpath("media/游戏").mkdir(parents=True)
        folder.joinpath("游戏.zip").write_bytes(b"rom")
        for name in ["boxfront.png", "logo.png", "video.mp4"]:
            folder.joinpath("media/游戏", name).write_bytes(b"media")
        launch = "launch: gpsp_rumble {file.path}\n" if platform == "GBA vib" else ""
        folder.joinpath("metadata.pegasus.txt").write_text(
            f"collection: {platform}\n{launch}\ngame: 游戏\nfile: 游戏.zip\n", encoding="utf-8"
        )
    template = tmp_path / "systems.xml"
    template.write_text(
        "<systemList><system><name>gba</name><fullname>GBA</fullname><path>%ROMPATH%/gba</path>"
        "<extension>.zip .gba</extension><command>retroarch %ROM%</command>"
        "<platform>gba</platform><theme>gba</theme></system></systemList>"
    )
    return HandheldConfig(
        source_root=root,
        device_rom_root="/storage/emulated/0/Test/Roms",
        esde_root="/storage/emulated/0/Test/ES-DE",
        systems_template=template,
        target_empty=True,
    )


def test_build_uses_ir_and_plan_without_copying_media(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    output = tmp_path / "job"
    summary = build_handheld(config, ["GBA"], output)
    assert summary["executable"] is True
    assert summary["roms"] == 1 and summary["media_targets"] == 3
    assert not (output / "downloaded_media").exists()
    xml = output / "files/gamelists/gba/gamelist.xml"
    assert etree.parse(str(xml)).findtext("game/path") == "./游戏.zip"
    # A platform selection limits game data, not the global configuration.
    systems = etree.parse(str(output / "files/custom_systems/es_systems.xml"))
    assert len(systems.findall("system")) == 76
    assert systems.find("system[name='GBA HACK']") is not None
    assert systems.find("system[name='GBA vib']") is not None
    for name in ("es_find_rules.xml", "es_import_rules.xml", "es_systems_sorting.xml"):
        assert (output / "files/custom_systems" / name).is_file()
    assert not (output / "files/gamelists/GBA vib").exists()
    script = (output / "apply.sh").read_bytes()
    assert not script.startswith(b"\xef\xbb\xbf") and b"\r" not in script
    assert b"cp -n -- " in script and b"check_source" not in script and b"check_config" not in script
    assert b"publish_config" not in script and b"gamelist.xml" not in script
    publication = json.loads((output / "publication.json").read_text(encoding="utf-8"))
    assert publication["roms"] == [config.device_rom_root + "/GBA/游戏.zip"]
    assert any(write["category"] == "gamelist" for write in publication["writes"])
    assert scan_handheld(config).game_count == 2
    with pytest.raises(ValidationError):
        build_handheld(config, ["GBA"], output)
    with pytest.raises(ValidationError):
        build_handheld(config, [], tmp_path / "empty")
    with pytest.raises(ValidationError):
        build_handheld(config, ["GBA"], config.source_root / "out")


def test_missing_snapshot_and_rumble_block_executable(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    config.target_empty = False
    summary = build_handheld(config, ["GBA"], tmp_path / "no-snapshot")
    assert not summary["executable"]
    assert not (tmp_path / "no-snapshot/apply.sh").exists()
    config.target_empty = True
    summary = build_handheld(config, ["GBA vib"], tmp_path / "rumble")
    assert not summary["executable"]
    assert not (tmp_path / "rumble/apply.sh").exists()
    complete = etree.parse(str(tmp_path / "rumble/files/custom_systems/es_systems.xml"))
    assert len(complete.findall("system")) == 76
    assert complete.find("system[name='GBA vib']") is not None
    assert (tmp_path / "rumble/files/gamelists/GBA vib/gamelist.xml").is_file()
    config.launch_overrides = {"GBA vib": "retroarch gpsp_rumble %ROM%"}
    config.confirmed_systems = ["GBA vib"]
    assert build_handheld(config, ["GBA vib"], tmp_path / "confirmed")["executable"]


def test_snapshot_merge_and_other_system_preserved(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    snapshot = tmp_path / "snapshot"
    snapshot.joinpath("gamelists/gba").mkdir(parents=True)
    snapshot.joinpath("gamelists/gba/gamelist.xml").write_text(
        "<gameList><game><path>./游戏.zip</path><name>User</name><favorite>true</favorite>"
        "<playtime>100</playtime></game></gameList>",
        encoding="utf-8",
    )
    snapshot.joinpath("custom_systems").mkdir()
    snapshot.joinpath("custom_systems/es_systems.xml").write_text(
        "<systemList><system><name>nes</name><path>/storage/nes</path></system></systemList>"
    )
    config.target_snapshot = snapshot
    output = tmp_path / "job"
    assert build_handheld(config, ["GBA"], output)["executable"]
    root = etree.parse(str(output / "files/gamelists/gba/gamelist.xml"))
    assert root.findtext("game/name") == "User"
    assert root.findtext("game/playtime") == "100"
    assert "nes" in (output / "files/custom_systems/es_systems.xml").read_text()
    plan = json.loads((output / "plan.json").read_text())
    assert any(op.get("expected_sha256") for op in plan["operations"] if op["kind"] == "write_text")


def test_config_cli_and_invalid_paths(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    path = tmp_path / "config.json"
    path.write_text(config.model_dump_json(), encoding="utf-8")
    loaded = HandheldConfig.load(path)
    assert loaded.source_root == config.source_root
    runner = CliRunner()
    assert runner.invoke(app, ["scan", "--config", str(path), "--json"]).exit_code == 0
    result = runner.invoke(
        app,
        ["build", "--config", str(path), "--platform", "GBA", "--out", str(tmp_path / "cli-job")],
    )
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["media_targets"] == 3
    path.write_text("{}")
    with pytest.raises(ValidationError):
        HandheldConfig.load(path)
    for invalid in ["/", "relative", "/storage/../other", "/storage/path\nline"]:
        with pytest.raises(ValidationError):
            android_path(invalid)


def archive(files: dict[str, bytes]) -> bytes:
    data = io.BytesIO()
    with tarfile.open(fileobj=data, mode="w") as tar:
        for name, content in files.items():
            entry = tarfile.TarInfo(name)
            entry.size = len(content)
            tar.addfile(entry, io.BytesIO(content))
    return data.getvalue()


def test_device_capture_downloads_only_metadata(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    metadata = config.source_root.joinpath("GBA/metadata.pegasus.txt").read_bytes()
    prefix = "/storage/emulated/0/Test/Roms"
    lines = f"{len(metadata)}|{prefix}/GBA/metadata.pegasus.txt\n3|{prefix}/GBA/游戏.zip\n5|{prefix}/GBA/media/游戏/boxfront.png\n"
    reader = AdbReader(Path("adb"), "test")
    with patch.object(
        reader,
        "read",
        side_effect=[lines.encode(), archive({"GBA/metadata.pegasus.txt": metadata}), b""],
    ):
        result = capture_device(
            reader, prefix, ["GBA"], config.esde_root, tmp_path / "catalog", config.systems_template
        )
    assert result["media_downloaded"] == 0
    assert (tmp_path / "catalog/Roms/GBA/游戏.zip").stat().st_size == 0
    assert (tmp_path / "catalog/Roms/GBA/metadata.pegasus.txt").read_bytes() == metadata
    captured = HandheldConfig.load(tmp_path / "catalog/config.json")
    summary = build_handheld(captured, ["GBA"], tmp_path / "captured-job")
    assert summary["media_bytes"] == 5
    with pytest.raises(ValidationError):
        _archive_files(archive({"../escape": b"bad"}))
    with pytest.raises(ValidationError):
        _archive_files(b"invalid tar")


def test_adb_requires_authorized_serial() -> None:
    reader = AdbReader(Path("adb"), "test")
    with patch("subprocess.run") as run:
        run.return_value.stdout = b"List of devices attached\ntest unauthorized\n"
        with pytest.raises(ValidationError):
            reader.read("true")
        assert run.call_count == 1


def test_custom_media_settings_and_existing_system_reuse(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    snapshot = tmp_path / "snapshot"
    snapshot.joinpath("custom_systems").mkdir(parents=True)
    snapshot.joinpath("custom_systems/es_systems.xml").write_text(
        "<systemList><system><name>mygba</name><path>/storage/emulated/0/Test/Roms/GBA</path>"
        "<command>existing %ROM%</command><theme>custom</theme></system></systemList>"
    )
    snapshot.joinpath("es_settings.xml").write_text(
        '<config><string name="MediaDirectory" value="/storage/emulated/0/Other/media"/></config>'
    )
    config.target_snapshot = snapshot
    output = tmp_path / "custom"
    assert build_handheld(config, ["GBA"], output)["executable"]
    assert (output / "files/gamelists/mygba/gamelist.xml").is_file()
    systems = etree.parse(str(output / "files/custom_systems/es_systems.xml"))
    assert systems.findtext("system[name='mygba']/theme") == "custom"
    assert systems.findtext("system[name='mygba']/command") == "existing %ROM%"
    script = (output / "apply.sh").read_text(encoding="utf-8")
    assert "/storage/emulated/0/Other/media/mygba/covers/" in script
    publication = json.loads((output / "publication.json").read_text(encoding="utf-8"))
    assert config.esde_root + "/es_settings.xml" in publication["guards"]
    config.media_root = "/storage/emulated/0/Wrong/media"
    with pytest.raises(ValidationError):
        build_handheld(config, ["GBA"], tmp_path / "wrong")


def test_missing_rom_blocks_and_templates_are_not_guessed(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    config.source_root.joinpath("GBA/游戏.zip").unlink()
    summary = build_handheld(config, ["GBA"], tmp_path / "missing-rom")
    assert not summary["executable"]
    config.systems_template = tmp_path / "missing-template.xml"
    summary = build_handheld(config, ["GBA vib"], tmp_path / "missing-template")
    assert any("template" in str(error) for error in summary["errors"])


@pytest.mark.parametrize("media", ["", "/storage/emulated/0/Other/media"])
def test_native_settings_fragments_and_explicit_system_id(tmp_path: Path, media: str) -> None:
    config = make_config(tmp_path)
    snapshot = tmp_path / "snapshot"
    settings = snapshot / "settings/es_settings.xml"
    settings.parent.mkdir(parents=True)
    raw = (
        '<?xml version="1.0"?>\n<bool name="ShowHiddenGames" value="false"/>\n'
        f'<string name="MediaDirectory" value="{media}"/>\n'
    ).encode()
    settings.write_bytes(raw)
    # Native settings take precedence over a legacy file at the root.
    snapshot.joinpath("es_settings.xml").write_text("invalid legacy settings")
    config.target_snapshot = snapshot
    config.system_ids = {"gba": "frontendtrans_gba"}
    output = tmp_path / "native"
    assert build_handheld(config, ["GBA"], output)["executable"]
    assert (output / "files/gamelists/frontendtrans_gba/gamelist.xml").is_file()
    systems = etree.parse(str(output / "files/custom_systems/es_systems.xml"))
    assert systems.findtext("system[name='frontendtrans_gba']/theme") == "gba"
    assert systems.findtext("system[name='frontendtrans_gba']/command") == "retroarch %ROM%"
    script = (output / "apply.sh").read_text(encoding="utf-8")
    expected_media = media or config.esde_root + "/downloaded_media"
    assert expected_media + "/frontendtrans_gba/covers/" in script
    publication = json.loads((output / "publication.json").read_text(encoding="utf-8"))
    assert publication["guards"][config.esde_root + "/settings/es_settings.xml"] == hashlib.sha256(raw).hexdigest()
    assert settings.read_bytes() == raw
    assert not (output / "files/settings").exists()


def test_explicit_mapping_reuses_existing_system_and_base_template(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    snapshot = tmp_path / "snapshot"
    systems = snapshot / "custom_systems/es_systems.xml"
    systems.parent.mkdir(parents=True)
    systems.write_text(
        "<systemList><system><name>existing_gba</name><fullname>User title</fullname>"
        "<path>/storage/emulated/0/Test/Roms/GBA</path><command>existing %ROM%</command>"
        "<theme>user-theme</theme></system></systemList>"
    )
    baseline = systems.read_bytes()
    config.target_snapshot = snapshot
    config.system_ids = {"gba": "frontendtrans_gba"}
    output = tmp_path / "reused"
    assert build_handheld(config, ["GBA"], output)["executable"]
    assert (output / "files/gamelists/existing_gba/gamelist.xml").is_file()
    root = etree.parse(str(output / "files/custom_systems/es_systems.xml"))
    assert len(root.findall("system[name='existing_gba']")) == 1
    assert root.findtext("system[name='existing_gba']/fullname") == "User title"
    assert root.findtext("system[name='existing_gba']/command") == "existing %ROM%"
    assert root.findtext("system[name='existing_gba']/theme") == "user-theme"
    assert root.findtext("system[name='existing_gba']/extension") == ".zip .gba"
    assert systems.read_bytes() == baseline


def test_adb_raw_output_and_remote_error_status() -> None:
    reader = AdbReader(Path("adb"), "test")

    def run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        if "devices" in command:
            return subprocess.CompletedProcess(command, 0, stdout=b"test device\n")
        marker = re.search(r"RETROLIBX_STATUS_[a-f0-9]+=", command[-1])
        assert marker is not None
        payload = b"raw\x00\r\nbytes\n" + marker.group().encode() + b"0"
        return subprocess.CompletedProcess(command, 0, stdout=payload)

    with patch("subprocess.run", side_effect=run):
        assert reader.read("printf 'raw'") == b"raw\x00\r\nbytes"
    with (
        patch(
            "subprocess.run",
            side_effect=[
                subprocess.CompletedProcess([], 0, stdout=b"test device\n"),
                subprocess.CompletedProcess([], 0, stdout=b"missing marker"),
            ],
        ),
        pytest.raises(ValidationError),
    ):
        reader.read("false")
