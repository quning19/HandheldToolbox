"""Small config publication and source capture with fully simulated ADB."""

import hashlib
import io
from pathlib import Path
import shlex
import tarfile

import pytest

from frontend_devices.adb import capture_pegasus_source
from library_converter.publication import AdbPublisher
from retrolibx.errors import ValidationError


class MemoryPublisher(AdbPublisher):
    def __init__(self, current=b"", failure=""):
        super().__init__(Path("unused-adb"), "mock-device")
        self.target = "/storage/1234/天马/GBA/savedeck.toml"
        self.files = {self.target: current} if current else {}
        self.failure, self.commands = failure, []

    def _digest(self, path):
        return hashlib.sha256(self.files[path]).hexdigest() if path in self.files else ""

    def read(self, command):
        self.commands.append(command)
        parts = shlex.split(command)
        if parts[0] == "cp":
            if self.failure == "backup":
                raise ValidationError("backup failed")
            self.files[parts[-1]] = self.files[parts[-2]]
        elif parts[0] == "mv":
            self.files[parts[-1]] = self.files.pop(parts[-2])
        elif parts[0] == "rm":
            self.files.pop(parts[-1], None)
        return b""

    def upload(self, source, destination):
        self.commands.append("push " + destination)
        self.files[destination] = b"truncated" if self.failure == "upload" else source.read_bytes()
        if self.failure == "concurrent":
            self.files[self.target] = b"user changed"
        return {"method": "C4", "applied": True}


def test_config_publication_backs_up_then_uploads_complete_filename(tmp_path):
    source = tmp_path / "savedeck.toml"
    source.write_bytes(b"new config")
    publisher = MemoryPublisher(b"old config")
    baseline = publisher._digest(publisher.target)
    publisher.publish_config(source, publisher.target, baseline)
    assert publisher.files[publisher.target] == b"new config"
    assert publisher.files[publisher.target + ".handheldtoolbox." + baseline + ".bak"] == b"old config"
    assert [c.split()[0] for c in publisher.commands] == ["cp", "push", "mv"]
    assert publisher.commands[1].endswith(".tmp")


@pytest.mark.parametrize("failure", ["backup", "upload", "concurrent"])
def test_publication_failure_never_replaces_the_original_config(tmp_path, failure):
    source = tmp_path / "savedeck.toml"
    source.write_bytes(b"new config")
    publisher = MemoryPublisher(b"old config", failure)
    with pytest.raises(ValidationError):
        publisher.publish_config(source, publisher.target, publisher._digest(publisher.target))
    assert publisher.files[publisher.target] == (b"user changed" if failure == "concurrent" else b"old config")
    assert not any(command.startswith("mv ") for command in publisher.commands)
    if failure == "backup":
        assert not any(command.startswith("push ") for command in publisher.commands)


def test_capture_downloads_configs_and_descriptors_and_uses_markers_for_resources(tmp_path):
    files = {"GBA/metadata.pegasus.txt": b"collection: GBA\n", "GBA/savedeck.toml": b'platform = "GBA"\ngames = []\n',
             "GBA/group.m3u": b"disc.cue\n", "GBA/disc.cue": b'FILE "track.bin" BINARY\n'}
    root = "/storage/1234/天马"
    commands = []

    class Reader:
        def read(self, command):
            commands.append(command)
            if command.startswith("find "):
                return "".join(root + "/" + name + "\0" for name in [*files, "GBA/rom.gba", "GBA/track.bin", "GBA/media/cover.png"]).encode()
            stream = io.BytesIO()
            with tarfile.open(fileobj=stream, mode="w") as archive:
                for name, raw in files.items():
                    item = tarfile.TarInfo(name)
                    item.size = len(raw)
                    archive.addfile(item, io.BytesIO(raw))
            return stream.getvalue()

    output = tmp_path / "capture"
    assert capture_pegasus_source(Reader(), root, output) == ["GBA"]
    assert (output / "GBA/rom.gba").read_bytes() == b""
    assert (output / "GBA/media/cover.png").read_bytes() == b""
    assert (output / "GBA/track.bin").read_bytes() == b""
    assert all((output / name).read_bytes() == raw for name, raw in files.items())
    assert "rom.gba" not in commands[1] and "cover.png" not in commands[1]
