"""Portable settings and user platform overrides over the shared XML catalog."""

from dataclasses import asdict, dataclass
import json
from pathlib import Path
import sys


@dataclass
class PlatformDefinition:
    id: str
    name: str
    directory: str
    parent: str = ""
    mode: str = "inherit"
    badge: str = ""


def default_definitions() -> list[PlatformDefinition]:
    from retrolibx.application.platform_catalog import bundled_registry
    registry = bundled_registry()
    definitions = [
        PlatformDefinition(
            record["name"], record.get("theme_label") or record["rom_directory"],
            record["rom_directory"], record.get("base_platform") or "",
            "separate" if record.get("base_platform") else "inherit",
            record.get("badge_text") or "",
        )
        for record in registry.records.values()
    ]
    if not any(item.id == "pspminis" for item in definitions):
        definitions.append(PlatformDefinition("pspminis", "PSP Minis", "PSP Minis", "psp"))
    return definitions


def app_directory() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    # In a source checkout, the launcher and settings share the project root.
    if (Path(__file__).resolve().parents[4] / "launch_gui.py").is_file():
        return Path(__file__).resolve().parents[4]
    return Path(sys.argv[0]).resolve().parent


def write_json(path: Path, content: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(content, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


class UiStore:
    """Portable settings and the platform definitions consumed by both workflows."""

    def __init__(self) -> None:
        self.settings_file = app_directory() / "settings.json"
        self.workspace = app_directory() / "workspace"
        self.theme = "light"
        if self.settings_file.is_file():
            content = json.loads(self.settings_file.read_text(encoding="utf-8"))
            if not isinstance(content, dict) or content.get("version") != 1 or not isinstance(content.get("workspace"), str):
                raise ValueError("基础设置格式无效；请保留文件并检查 settings.json。")
            self.workspace = Path(content["workspace"])
            if not self.workspace.is_absolute():
                raise ValueError("settings.json 中的工作目录必须是绝对路径。")
            self.theme = content.get("theme", "light")
            if self.theme not in {"light", "dark"}:
                raise ValueError("settings.json 中的 theme 必须为 light 或 dark。")
        self.definitions = self.read_definitions(self.workspace)

    @staticmethod
    def read_definitions(workspace: Path) -> list[PlatformDefinition]:
        path = workspace / "config" / "platforms.json"
        if not path.is_file():
            return default_definitions()
        content = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(content, dict) or content.get("version") != 1 or not isinstance(content.get("platforms"), list):
            raise ValueError("平台配置版本无效。")
        definitions = [PlatformDefinition(**item) for item in content["platforms"]]
        for item in definitions:
            if not all(isinstance(value, str) for value in asdict(item).values()):
                raise ValueError("平台字段必须是文字。")
        ids = {item.id for item in definitions}
        if len(ids) != len(definitions):
            raise ValueError("平台内部标识重复。")
        directories = [item.directory.casefold() for item in definitions]
        if len(set(directories)) != len(directories):
            raise ValueError("平台 ROM 目录重复。")
        for item in definitions:
            if not item.name.strip() or not item.id.strip() or not valid_component(item.directory):
                raise ValueError("平台名称、标识或 ROM 目录无效。")
            if item.mode not in {"inherit", "separate"}:
                raise ValueError("平台主题表现无效。")
            visited = {item.id}
            parent = item.parent
            while parent:
                if parent not in ids or parent in visited:
                    raise ValueError("平台母体引用缺失或存在循环。")
                visited.add(parent)
                parent = next(entry.parent for entry in definitions if entry.id == parent)
        return definitions

    def change_workspace(self, directory: Path) -> None:
        directory = directory.resolve()
        definitions = self.read_definitions(directory)
        for name in ("config", "themes/original", "themes/exported", "library", "devices", "logs", "temp"):
            (directory / name).mkdir(parents=True, exist_ok=True)
        write_json(self.settings_file, {"version": 1, "workspace": str(directory), "theme": self.theme})
        self.workspace, self.definitions = directory, definitions

    def save_theme(self, mode: str) -> None:
        if mode not in {"light", "dark"}:
            raise ValueError("无效的界面主题。")
        write_json(self.settings_file, {"version": 1, "workspace": str(self.workspace), "theme": mode})
        self.theme = mode

    def save_definitions(self, definitions: list[PlatformDefinition]) -> None:
        write_json(self.workspace / "config" / "platforms.json", {
            "version": 1, "platforms": [asdict(item) for item in definitions],
        })
        self.definitions = definitions


def valid_component(value: str) -> bool:
    return bool(value.strip()) and value not in {".", ".."} and not any(
        character in value for character in '/\\:*?"<>|\r\n\t\x00'
    ) and not value.endswith((" ", "."))
