"""One-time source relocation; file editing only, never imports product code."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
mapping = {
    "retrolibx.application.desktop": "library_converter.desktop",
    "retrolibx.application.device": "frontend_devices.adb",
    "retrolibx.application.deployment": "library_converter.deployment",
    "retrolibx.application.handheld": "library_converter.handheld",
    "retrolibx.application.publication": "library_converter.publication",
    "retrolibx.application.selection": "library_converter.selection",
    "retrolibx.application.platform_catalog": "frontend_platforms.catalog",
    "retrolibx.application.themes": "theme_converter.service",
    "retrolibx.application.theme_badges": "theme_converter.badges",
    "retrolibx.gui.state": "frontend_common.state",
    "retrolibx.gui": "frontend_gui",
}
for directory in ("src", "tests"):
    for path in (ROOT / directory).rglob("*.py"):
        text = path.read_text(encoding="utf-8-sig")
        for old, new in mapping.items():
            text = text.replace(old, new)
        if directory == "tests":
            text = text.replace('parents[1] / "src', 'parents[2] / "src')
        path.write_text(text, encoding="utf-8")

for path in (ROOT / "src/library_converter").glob("*.py"):
    text = path.read_text(encoding="utf-8")
    for old, new in {
        "from .device import": "from frontend_devices.adb import",
        "from .platform_catalog import": "from frontend_platforms.catalog import",
        "from .service import": "from retrolibx.application.service import",
        "from .shared_media import": "from retrolibx.application.shared_media import",
    }.items():
        text = text.replace(old, new)
    path.write_text(text, encoding="utf-8")

desktop = ROOT / "src/library_converter/desktop.py"
text = desktop.read_text(encoding="utf-8")
start, end = text.index("def find_adb()"), text.index("@dataclass\nclass PlatformInfo:")
header = '''"""Device discovery independent of converters and Qt."""
from dataclasses import dataclass
from pathlib import Path
import json
import os
import shlex
import shutil
import subprocess
import sys
from retrolibx.errors import ValidationError
from .adb import AdbReader

'''
(ROOT / "src/frontend_devices/discovery.py").write_text(header + text[start:end], encoding="utf-8")
text = text[:start] + "from frontend_devices.discovery import Device, discover_device, find_adb\n\n\n" + text[end:]
desktop.write_text(text, encoding="utf-8")
device = ROOT / "src/frontend_devices/adb.py"
device.write_text(device.read_text(encoding="utf-8").replace(
    "from .selection import detect_metadata_encoding", "from retrolibx.utils.encoding import detect_metadata_encoding"), encoding="utf-8")

state = ROOT / "src/frontend_gui/state.py"
(ROOT / "src/frontend_common/state.py").write_text(state.read_text(encoding="utf-8"), encoding="utf-8")
state.write_text('"""Compatibility import; portable configuration has no Qt dependency."""\nfrom frontend_common.state import PlatformDefinition, UiStore, app_directory, default_definitions, valid_component, write_json\n', encoding="utf-8")
for name in ("library_converter", "theme_converter", "frontend_devices", "frontend_common"):
    (ROOT / "src" / name / "__init__.py").write_text('"""Independent FrontendTransTool component."""\n', encoding="utf-8")

catalog = ROOT / "src/frontend_platforms/catalog.py"
catalog.write_text(catalog.read_text(encoding="utf-8").replace(
    'Path(__file__).parents[2] / "frontend_platforms/custom_systems-PG"',
    'Path(__file__).with_name("custom_systems-PG")'), encoding="utf-8")

for path in (ROOT / "tests").rglob("*.py"):
    text = path.read_text(encoding="utf-8")
    if "discovery" in path.name:
        text = text.replace("library_converter.desktop", "frontend_devices.discovery")
    if path.name == "test_desktop_business.py":
        marker = "    def test_device_discovery_uses_authorized_serial_and_shallow_root_counts(self):"
        a = text.index(marker)
        b = text.index("    def ", a + len(marker))
        text = text[:a] + text[a:b].replace("library_converter.desktop", "frontend_devices.discovery") + text[b:]
    path.write_text(text, encoding="utf-8")

pth = ROOT / "retrolibx/.venv/Lib/site-packages/_editable_impl_retrolibx.pth"
if pth.is_file():
    pth.write_text(str(ROOT / "src") + "\n", encoding="utf-8")
