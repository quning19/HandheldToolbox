"""Deployment/launch cases; running them requires separate user approval."""
import json
from pathlib import Path
from unittest.mock import Mock, patch

from lxml import etree
import pytest
from typer.testing import CliRunner

from retrolibx.application.deployment import DeploymentStage, deploy_task, plan_deployment
from retrolibx.application.handheld import HandheldConfig, build_handheld
from retrolibx.application.publication import AdbPublisher
from retrolibx.cli import app
from retrolibx.core.android import android_intent_command
from retrolibx.errors import ValidationError


LAUNCH = (
    "am start --user 0 -n com.retroarch.aarch64/com.retroarch.browser.retroactivity.RetroActivityFuture "
    "-e ROM {file.path} -e LIBRETRO /data/data/com.retroarch.aarch64/cores/gpsp_rumble_libretro_android.so "
    "-e CONFIGFILE /storage/emulated/0/Android/data/com.retroarch.aarch64/files/retroarch.cfg --activity-clear-top"
)
REMOTE = "/storage/emulated/0/Download/中文任务/apply.sh"


def config(tmp_path: Path, platforms=("GBA",)) -> HandheldConfig:
    root = tmp_path / "Roms"
    for platform in platforms:
        folder = root / platform
        folder.joinpath("media/游戏").mkdir(parents=True)
        folder.joinpath("游戏.zip").write_bytes(b"rom")
        folder.joinpath("media/游戏/boxfront.png").write_bytes(b"cover")
        folder.joinpath("metadata.pegasus.txt").write_bytes(
            (f"collection: {platform}\nlaunch: {LAUNCH}\n\ngame: 游戏\nfile: 游戏.zip\n").encode("utf-8")
        )
    return HandheldConfig(source_root=root, device_rom_root="/storage/emulated/0/Test/Roms",
                          esde_root="/storage/emulated/0/Test/ES-DE", target_empty=True)


def test_multi_platform_build_and_explicit_metadata_launch(tmp_path):
    settings = config(tmp_path, ("GBA", "GBA vib"))
    settings.metadata_launch_systems = ["GBA vib"]
    task = tmp_path / "task"
    summary = build_handheld(settings, ["GBA", "GBA vib"], task)
    assert summary["executable"] and summary["roms"] == 2 and summary["media_targets"] == 2
    root = etree.fromstring((task / "files/custom_systems/es_systems.xml").read_bytes())
    commands = root.findall("system[name='GBA vib']/command")
    assert len(commands) == 1 and commands[0].text == android_intent_command(LAUNCH)
    assert len(root.findall("system[name='gba']/command")) > 1
    assert (task / "files/gamelists/gba/gamelist.xml").is_file()
    assert (task / "files/gamelists/GBA vib/gamelist.xml").is_file()
    assert b"\r" not in (task / "apply.sh").read_bytes()


def test_launch_preserves_component_core_config_and_flag():
    value = android_intent_command(LAUNCH)
    assert value.startswith("%ANDROIDAPP%=com.retroarch.aarch64/com.retroarch.browser.retroactivity.RetroActivityFuture ")
    assert "%EXTRA_ROM%=%ROMRAW%" in value
    assert "%EXTRA_LIBRETRO%=/data/data/com.retroarch.aarch64/cores/gpsp_rumble_libretro_android.so" in value
    assert "%EXTRA_CONFIGFILE%=/storage/emulated/0/Android/data/com.retroarch.aarch64/files/retroarch.cfg" in value
    assert value.endswith(" %ACTIVITY_CLEAR_TOP%")


def test_unsupported_launch_is_not_silently_dropped():
    for command in (LAUNCH + " --unsupported", LAUNCH.replace("--user 0", "--user 10"), LAUNCH + " -e"):
        with pytest.raises(ValidationError):
            android_intent_command(command)


def test_explicit_template_and_existing_node_positions_are_preserved(tmp_path):
    settings = config(tmp_path, ("GBA", "PSP Minis"))
    snapshot = tmp_path / "snapshot"
    snapshot.joinpath("custom_systems").mkdir(parents=True)
    snapshot.joinpath("custom_systems/es_systems.xml").write_bytes(
        b"<systemList><system><name>gba</name><fullname>Original</fullname><path>%ROMPATH%/GBA</path>"
        b"<command>custom %ROM%</command></system><system><name>psp</name><path>%ROMPATH%/PSP</path>"
        b"<command>current-psp %ROM%</command><theme>psp-custom</theme><platform>psp</platform></system></systemList>"
    )
    settings.target_snapshot = snapshot
    settings.system_ids = {"psp-minis": "pspminis"}
    settings.system_templates = {"psp-minis": "psp"}
    task = tmp_path / "task"
    assert build_handheld(settings, ["GBA", "PSP Minis"], task)["executable"]
    root = etree.fromstring((task / "files/custom_systems/es_systems.xml").read_bytes())
    assert [node.findtext("name") for node in root.findall("system")][:2] == ["gba", "psp"]
    assert root.findtext("system[name='gba']/path") == "%ROMPATH%/GBA"
    assert root.findtext("system[name='gba']/command") == "custom %ROM%"
    assert root.findtext("system[name='pspminis']/command") == "current-psp %ROM%"
    assert root.findtext("system[name='pspminis']/theme") == "psp-custom"
    assert root.findtext("system[name='pspminis']/extension")


def test_deploy_preview_has_no_adb_or_resource_audit(tmp_path):
    task = tmp_path / "task"
    build_handheld(config(tmp_path), ["GBA"], task)
    with patch("retrolibx.application.device.subprocess.run") as run:
        result = CliRunner().invoke(app, ["deploy", str(task), "--adb", "adb", "--serial", "authorized",
                                        "--remote", REMOTE, "--skip-platform-config"])
    assert result.exit_code == 0, result.output
    preview = json.loads(result.stdout)
    assert preview["steps"] == ["upload", "copy", "publish"] and preview["resource_audits"] == []
    assert preview["upload"]["method"] == "C4"
    assert len(preview["publication"]["writes"]) == 1
    run.assert_not_called()


def test_copy_failure_keeps_timing_and_stops_before_xml_publication(tmp_path):
    task = tmp_path / "task"
    build_handheld(config(tmp_path), ["GBA"], task)
    client = Mock(spec=AdbPublisher, serial="authorized")
    client.upload.return_value = {"applied": True}
    client.read.side_effect = ValidationError("cp failed")
    with pytest.raises(ValidationError, match="cp failed"):
        deploy_task(client, task, REMOTE, skip_platform_config=True)
    client.publish.assert_not_called()
    result = json.loads((task / "deployment-result.json").read_text(encoding="utf-8"))
    assert result["status"] == "failed"
    assert [phase["status"] for phase in result["phases"]] == ["completed", "failed"]
    assert result["phases"][-1]["seconds"] >= 0


def test_separate_approved_stages_keep_previous_times(tmp_path):
    task = tmp_path / "task"
    build_handheld(config(tmp_path), ["GBA"], task)
    client = Mock(spec=AdbPublisher, serial="authorized")
    client.upload.return_value = {"applied": True}
    client.read.return_value = b""
    deploy_task(client, task, REMOTE, DeploymentStage.UPLOAD, True)
    result = deploy_task(client, task, REMOTE, DeploymentStage.COPY, True)
    assert [phase["stage"] for phase in result["phases"]] == ["upload", "copy"]
    client.publish.assert_not_called()
    client.read.assert_called_once_with(plan_deployment(task, REMOTE)["copy_command"], timeout=3600)


def test_crlf_script_is_rejected_before_device_contact(tmp_path):
    task = tmp_path / "task"
    build_handheld(config(tmp_path), ["GBA"], task)
    script = task / "apply.sh"
    script.write_bytes(script.read_bytes().replace(b"\n", b"\r\n"))
    client = Mock(spec=AdbPublisher, serial="authorized")
    with pytest.raises(ValidationError, match="UTF-8/LF"):
        deploy_task(client, task, REMOTE)
    client.upload.assert_not_called()
    client.read.assert_not_called()
    client.publish.assert_not_called()
