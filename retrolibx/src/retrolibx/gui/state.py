"""Portable UI settings and explicit example data, separate from conversion models."""

from dataclasses import asdict, dataclass, replace
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


@dataclass
class PlatformPreview:
    id: str
    name: str
    art: str
    roms: int
    covers: int
    existing: int
    missing_references: int = 0


@dataclass
class ThemePreview:
    name: str
    original: bool
    converted: bool
    device: bool | None = None


PLATFORM_PREVIEWS = [
    PlatformPreview("gb", "GB", "gb", 128, 128, 128),
    PlatformPreview("gba", "GBA", "gba", 20, 18, 18, 80),
    PlatformPreview("gba-hack", "GBA hack", "GBA hack", 86, 86, 86),
    PlatformPreview("gba-vib", "GBA vib", "GBA vib", 24, 24, 24),
    PlatformPreview("nes", "FC", "nes", 186, 184, 186),
    PlatformPreview("gbc", "GBC", "gbc", 75, 75, 75),
    PlatformPreview("megadrive", "MD", "megadrive", 112, 112, 112),
    PlatformPreview("gc", "NGC", "gc", 32, 32, 32),
    PlatformPreview("n64", "N64", "n64", 70, 70, 70),
    PlatformPreview("psx", "PS1", "psx", 64, 64, 64),
    PlatformPreview("psp", "PSP", "psp", 88, 88, 88),
    PlatformPreview("pspminis", "PSP Minis", "psp", 30, 30, 0),
    PlatformPreview("sfc", "SFC", "sfc", 167, 167, 167),
    PlatformPreview("saturn", "SS", "saturn", 41, 41, 41),
    PlatformPreview("wsc", "WSC", "wonderswan", 48, 47, 48),
]


def default_definitions() -> list[PlatformDefinition]:
    parents = {"gba-hack": "gba", "gba-vib": "gba", "pspminis": "psp"}
    badges = {"gba-hack": "HACK", "gba-vib": "VIB"}
    definitions = [
        PlatformDefinition(
            item.id, item.name, item.name, parents.get(item.id, ""),
            "separate" if item.id in badges else "inherit", badges.get(item.id, ""),
        )
        for item in PLATFORM_PREVIEWS
    ]
    definitions.extend([
        PlatformDefinition("sfc-hack", "SFC hack", "SFC hack", "sfc", "separate", "HACK"),
        PlatformDefinition("sfc-msu1", "SFC-MSU1", "SFC-MSU1", "sfc", "separate", "MSU1"),
    ])
    return definitions


def example_platforms(definitions: list[PlatformDefinition], source: str) -> list[PlatformPreview]:
    """Example counts only; never inspects the selected filesystem or ADB device."""
    samples = {item.id: item for item in PLATFORM_PREVIEWS}
    # Internal storage intentionally contains fewer example platforms than SD.
    allowed = {"gb", "gba", "nes", "psp"} if source == "internal" else samples.keys()
    return [replace(samples[item.id], name=item.name) for item in definitions if item.id in allowed]


def example_themes() -> list[ThemePreview]:
    return [
        ThemePreview("Canvas", True, True),
        ThemePreview("Aura", True, False),
        ThemePreview("Alekfull NX", True, True),
        ThemePreview("Elementerial", False, False),
        ThemePreview("Iconic", True, False),
        ThemePreview("iiSU Interpreted", False, False),
        ThemePreview("PlayStation-X", True, True),
    ]


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
    """Only GUI settings/platform definitions persist. Preview task results do not."""

    def __init__(self) -> None:
        self.settings_file = app_directory() / "settings.json"
        self.workspace = app_directory() / "workspace"
        if self.settings_file.is_file():
            content = json.loads(self.settings_file.read_text(encoding="utf-8"))
            if not isinstance(content, dict) or content.get("version") != 1 or not isinstance(content.get("workspace"), str):
                raise ValueError("基础设置格式无效；请保留文件并检查 settings.json。")
            self.workspace = Path(content["workspace"])
            if not self.workspace.is_absolute():
                raise ValueError("settings.json 中的工作目录必须是绝对路径。")
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
        write_json(self.settings_file, {"version": 1, "workspace": str(directory)})
        self.workspace, self.definitions = directory, definitions

    def save_definitions(self, definitions: list[PlatformDefinition]) -> None:
        write_json(self.workspace / "config" / "platforms.json", {
            "version": 1, "platforms": [asdict(item) for item in definitions],
        })
        self.definitions = definitions


def valid_component(value: str) -> bool:
    return bool(value.strip()) and value not in {".", ".."} and not any(
        character in value for character in '/\\:*?"<>|\r\n\t\x00'
    ) and not value.endswith((" ", "."))
