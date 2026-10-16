import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from frontend_devices.adb import AdbUploader
from retrolibx.cli import app
from retrolibx.errors import ValidationError


def test_directory_contents_use_c2_and_preserve_unicode(tmp_path: Path) -> None:
    source = tmp_path / "中文主题"
    source.mkdir()
    source.joinpath("主题.xml").write_bytes(b"theme")
    source.joinpath("empty").mkdir()
    remote = "/storage/emulated/0/ES-DE/themes/中文 '主题"
    client = AdbUploader(Path("adb"), "authorized")
    with patch.object(client, "read", return_value=b"") as prepare, patch(
        "frontend_devices.adb.subprocess.run"
    ) as run:
        result = client.upload(source, remote)
    command = run.call_args.args[0]
    assert command == ["adb", "-s", "authorized", "push", str(source.absolute()) + "/.", remote + "/"]
    script = prepare.call_args.args[0]
    assert "mkdir -p --" in script and "'\"'\"'" in script
    assert result["method"] == "C2" and result["files"] == 1 and result["deletions"] == 0


def test_selected_file_uses_c4_without_uploading_its_siblings(tmp_path: Path) -> None:
    source = tmp_path / "中文配置.xml"
    source.write_bytes(b"selected")
    source.with_name("unselected.xml").write_bytes(b"leave this file alone")
    remote = "/storage/emulated/0/ES-DE/custom_systems/中文配置.xml"
    client = AdbUploader(Path("adb"), "authorized")
    with patch.object(client, "read", return_value=b"") as prepare, patch(
        "frontend_devices.adb.subprocess.run"
    ) as run:
        result = client.upload(source, remote)
    assert run.call_args.args[0][-2:] == [str(source.absolute()), remote]
    assert "mkdir -p -- /storage/emulated/0/ES-DE/custom_systems" in prepare.call_args.args[0]
    assert "test -f" in prepare.call_args.args[0]
    assert result["method"] == "C4" and result["files"] == 1


def test_file_parent_destination_is_rejected_before_adb(tmp_path: Path) -> None:
    source = tmp_path / "file.xml"
    source.write_bytes(b"file")
    client = AdbUploader(Path("adb"), "authorized")
    with patch("frontend_devices.adb.subprocess.run") as run:
        with pytest.raises(ValidationError, match="complete remote filename"):
            client.upload(source, "/storage/emulated/0/ES-DE/custom_systems/")
    run.assert_not_called()


def test_upload_requires_authorized_device_before_any_write(tmp_path: Path) -> None:
    source = tmp_path / "file.xml"
    source.write_bytes(b"file")
    client = AdbUploader(Path("adb"), "unauthorized")
    with patch("frontend_devices.adb.subprocess.run") as run:
        run.return_value.stdout = b"List of devices attached\nunauthorized unauthorized\n"
        with pytest.raises(ValidationError, match="not authorized"):
            client.upload(source, "/storage/emulated/0/ES-DE/file.xml")
    assert run.call_count == 1
    assert run.call_args.args[0] == ["adb", "devices", "-l"]


def test_cli_upload_previews_without_contacting_a_device(tmp_path: Path) -> None:
    source = tmp_path / "file.xml"
    source.write_bytes(b"file")
    with patch("frontend_devices.adb.subprocess.run") as run:
        result = CliRunner().invoke(app, [
            "upload", str(source), "--adb", "adb", "--serial", "authorized",
            "--remote", "/storage/emulated/0/ES-DE/file.xml",
        ])
    assert result.exit_code == 0, result.output
    assert '"applied": false' in result.stdout and '"method": "C4"' in result.stdout
    run.assert_not_called()


def test_failed_push_reports_partial_destination_without_deleting_it(tmp_path: Path) -> None:
    source = tmp_path / "file.xml"
    source.write_bytes(b"file")
    client = AdbUploader(Path("adb"), "authorized")
    with patch.object(client, "read", return_value=b""), patch(
        "frontend_devices.adb.subprocess.run",
        side_effect=subprocess.CalledProcessError(1, "adb push"),
    ) as run:
        with pytest.raises(ValidationError, match="partial files"):
            client.upload(source, "/storage/emulated/0/ES-DE/file.xml")
    assert run.call_count == 1
