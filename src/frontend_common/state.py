"""Portable preferences shared by GUI and headless tools."""
import json
from pathlib import Path
import sys
from frontend_common.files import write_json
from frontend_platforms.user_catalog import (
    PlatformDefinition, default_definitions, valid_component, load_catalog, save_catalog,
)

CARD_STYLES = {"canvas": "Canvas", "aura": "Aura", "alekfull-nx": "Alekfull NX", "iisu": "iiSU Interpreted"}


def app_directory() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    for ancestor in Path(__file__).resolve().parents:
        if (ancestor / "launch_gui.py").is_file():
            return ancestor
    return Path(sys.argv[0]).resolve().parent


class UiStore:
    def __init__(self) -> None:
        self.settings_file = app_directory() / "settings.json"
        self.workspace = app_directory() / "workspace"
        self.theme, self.card_style = "light", "canvas"
        if self.settings_file.is_file():
            content = json.loads(self.settings_file.read_text(encoding="utf-8"))
            if not isinstance(content, dict) or content.get("version") != 1 or not isinstance(content.get("workspace"), str):
                raise ValueError("基础设置格式无效；请保留文件并检查 settings.json。")
            self.workspace = Path(content["workspace"])
            if not self.workspace.is_absolute():
                raise ValueError("settings.json 中的工作目录必须是绝对路径。")
            self.theme = content.get("theme", "light")
            self.card_style = content.get("card_style", "canvas")
            if self.theme not in {"light", "dark"} or self.card_style not in CARD_STYLES:
                raise ValueError("settings.json 中的外观或平台卡片风格无效。")
        self.definitions, self.catalog_notices = load_catalog(self.workspace)

    @staticmethod
    def read_definitions(workspace):
        return load_catalog(workspace)[0]

    def _save_settings(self, **changes):
        data = {"version": 1, "workspace": str(self.workspace), "theme": self.theme, "card_style": self.card_style}
        data.update(changes)
        write_json(self.settings_file, data)

    def change_workspace(self, directory: Path) -> None:
        directory = directory.resolve()
        definitions, notices = load_catalog(directory)
        for name in ("config", "themes/original", "themes/exported", "library", "devices", "backups", "logs", "temp"):
            (directory / name).mkdir(parents=True, exist_ok=True)
        self._save_settings(workspace=str(directory))
        self.workspace, self.definitions, self.catalog_notices = directory, definitions, notices

    def save_theme(self, mode: str) -> None:
        if mode not in {"light", "dark"}:
            raise ValueError("无效的界面主题。")
        self._save_settings(theme=mode)
        self.theme = mode

    def save_card_style(self, style: str) -> None:
        if style not in CARD_STYLES:
            raise ValueError("无效的平台卡片风格。")
        self._save_settings(card_style=style)
        self.card_style = style

    def save_definitions(self, definitions: list[PlatformDefinition]) -> None:
        save_catalog(self.workspace, definitions)
        self.definitions, self.catalog_notices = load_catalog(self.workspace)
