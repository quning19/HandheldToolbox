"""Host publication phase regressions; execution needs explicit approval."""
import hashlib
import json
import shlex
from pathlib import Path

import pytest

from retrolibx.application.handheld import HandheldConfig, build_handheld
from retrolibx.application.publication import AdbPublisher, load_publication, plan_publication
from retrolibx.errors import ValidationError


def task(tmp_path: Path, shared: bool = False) -> Path:
    folder = tmp_path / "source/GBA"
    folder.joinpath("media/Game").mkdir(parents=True)
    folder.joinpath("Game.zip").write_bytes(b"rom")
    folder.joinpath("media/Game/boxfront.jpg").write_bytes(b"cover")
    folder.joinpath("metadata.pegasus.txt").write_text("collection: GBA\n\ngame: Game\nfile: Game.zip\n", encoding="utf-8")
    output = tmp_path / "task"
    build_handheld(HandheldConfig(
        source_root=folder.parent, device_rom_root="/storage/emulated/0/Test/Roms",
        esde_root="/storage/emulated/0/Test/ES-DE", target_empty=True, shared_pegasus=shared,
    ), ["GBA"], output)
    return output


class MemoryPublisher(AdbPublisher):
    def __init__(self, folder: Path, failure: str = ""):
        super().__init__(Path("adb.exe"), "mock-device")
        self.failure, self.commands, self.states, self.media_calls = failure, [], {}, 0
        data, _ = load_publication(folder, True)
        for write in data["writes"]:
            if write["expected_sha256"]:
                self.states[write["destination"]] = write["expected_sha256"]
        for item in data["cleanup"]:
            self.states[item["source"]] = hashlib.sha256(b"cover").hexdigest()

    def _safe_paths(self, paths):
        pass

    def _digest(self, path):
        return self.states.get(path, "")

    def _media(self, data, task):
        self.media_calls += 1
        if self.failure == "missing-media" or (self.failure == "changed-before-cleanup" and self.media_calls > 1):
            raise ValidationError("Media copy is incomplete/different")
        return {item["receipt_key"]: hashlib.sha256(b"cover").hexdigest()
                for item in data["media"] if item["receipt_key"]}

    def read(self, command):
        self.commands.append(command)
        words = shlex.split(command)
        if words[:2] == ["mv", "--"]:
            self.states[words[3]] = self.states.pop(words[2])
        elif words[:2] == ["cp", "--"]:
            self.states[words[3]] = self.states[words[2]]
        elif words[:2] == ["rm", "-f"]:
            self.states.pop(words[-1], None)
        return b""

    def upload(self, source, destination):
        self.commands.append("push " + destination)
        self.states[destination] = "0" * 64 if self.failure == "bad-push" else hashlib.sha256(source.read_bytes()).hexdigest()
        return {"applied": True}


def test_media_only_script_and_host_preview_skip_platform_config(tmp_path):
    folder = task(tmp_path)
    script = (folder / "apply.sh").read_text(encoding="utf-8")
    assert script.splitlines()[1] == "set -e"
    assert "cp -n -- " in script and "sha256sum" not in script and "trap " not in script
    assert "publish_config" not in script and "gamelist.xml" not in script
    preview = plan_publication(folder, True)
    assert len(preview["writes"]) == 1 and preview["writes"][0]["category"] == "gamelist"
    assert preview["source_cleanup"] == [] and preview["device_script_executes"] is False


def test_incomplete_shared_media_blocks_all_publication_writes(tmp_path):
    folder = task(tmp_path, True)
    publisher = MemoryPublisher(folder, "missing-media")
    with pytest.raises(ValidationError, match="Media"):
        publisher.publish(folder, True)
    assert not any(command.startswith(("push ", "cp ", "mv ", "rm ")) for command in publisher.commands)


def test_bad_adb_payload_never_replaces_gamelist(tmp_path):
    folder = task(tmp_path)
    publisher = MemoryPublisher(folder, "bad-push")
    destination = plan_publication(folder, True)["writes"][0]["destination"]
    with pytest.raises(ValidationError, match="payload differs"):
        publisher.publish(folder, True)
    assert destination not in publisher.states
    assert not any(command.startswith("mv ") for command in publisher.commands)


def test_shared_target_change_after_metadata_keeps_source_media(tmp_path):
    folder = task(tmp_path, True)
    data = json.loads((folder / "publication.json").read_text(encoding="utf-8"))
    publisher = MemoryPublisher(folder, "changed-before-cleanup")
    with pytest.raises(ValidationError, match="Media"):
        publisher.publish(folder, True)
    for item in data["cleanup"]:
        assert item["source"] in publisher.states
    assert not any(command.startswith("rm ") for command in publisher.commands)


def test_gamelist_baseline_drift_stops_before_push(tmp_path):
    folder = task(tmp_path)
    publisher = MemoryPublisher(folder)
    destination = plan_publication(folder, True)["writes"][0]["destination"]
    publisher.states[destination] = hashlib.sha256(b"external edit").hexdigest()
    with pytest.raises(ValidationError, match="Device file changed"):
        publisher.publish(folder, True)
    assert not any(command.startswith("push ") for command in publisher.commands)
