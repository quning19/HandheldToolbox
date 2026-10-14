"""Shared platform definitions and recognition, compatible with Python 3.9+."""

from __future__ import annotations

import json
import unicodedata
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET


CONFIGURATION_FILES = (
    "es_systems.xml",
    "es_find_rules.xml",
    "es_import_rules.xml",
    "es_systems_sorting.xml",
)


def _configuration_directory(
    document: dict[str, Any], source: Path, config_dir: Path | None
) -> Path:
    directory: Path | None
    if config_dir is not None:
        directory = config_dir.resolve()
    else:
        configured = document.get("system_config_dir")
        directory = (source.parent / configured).resolve() if configured else None
        # The explicitly declared bundled copy supports installations without the theme project.
        if directory is None or not directory.exists():
            directory = (source.parent / document["bundled_system_config_dir"]).resolve()
    if not directory.is_dir():
        raise ValueError("Platform configuration directory is missing: " + str(directory))
    for name in CONFIGURATION_FILES:
        if not (directory / name).is_file():
            raise ValueError("Platform configuration file is missing: " + str(directory / name))
    return directory


def platform_configuration(config_dir: Path | None = None) -> dict[str, str]:
    """Read the complete XML set from the same source used for platform recognition."""
    source = Path(__file__).with_name("platforms.json")
    document = json.loads(source.read_text(encoding="utf-8"))
    directory = _configuration_directory(document, source, config_dir)
    return {
        name: (directory / name).read_bytes().decode("utf-8")
        for name in CONFIGURATION_FILES
    }


def platform_component(value: str) -> str:
    """Accept real theme names, including spaces, without accepting path syntax."""
    if (
        not value
        or value in {".", ".."}
        or value != value.strip()
        or value.endswith(".")
        or any(ord(char) < 32 or char in '/\\<>:"|?*' for char in value)
    ):
        raise ValueError(f"Invalid platform name: {value!r}")
    return value


def platform_key(value: str) -> str:
    return unicodedata.normalize("NFC", value).strip().casefold()


class PlatformRegistry:
    def __init__(self, document: dict[str, Any]) -> None:
        if document.get("version") != 1:
            raise ValueError("Unsupported platform configuration version")
        self.records: dict[str, dict[str, Any]] = {}
        self.aliases: dict[str, set[str]] = {}
        self.config_dir: Path | None = None
        for record in document["platforms"]:
            name = platform_component(record["name"])
            if name in self.records:
                raise ValueError("Duplicate platform: " + name)
            platform_component(record["rom_directory"])
            platform_component(record["theme"])
            self.records[name] = record
            for alias in [name, record["rom_directory"], record["theme"], *record["aliases"]]:
                self.aliases.setdefault(platform_key(alias), set()).add(name)
        for record in self.records.values():
            if record.get("base_platform") not in (None, *self.records):
                raise ValueError("Unknown base platform: " + record["name"])

    @classmethod
    def load(
        cls, path: Path | None = None, config_dir: Path | None = None
    ) -> PlatformRegistry:
        source = path or Path(__file__).with_name("platforms.json")
        document = json.loads(source.read_text(encoding="utf-8"))
        if document.get("version") != 2:
            raise ValueError("Unsupported platform supplement configuration version")
        directory = _configuration_directory(document, source, config_dir)
        raw = (directory / "es_systems.xml").read_bytes()
        if b"<!doctype" in raw.lower():
            raise ValueError("DTD is not supported in platform XML")
        try:
            root = ET.fromstring(raw)
        except ET.ParseError as exc:
            raise ValueError("Invalid platform XML: " + str(exc)) from exc
        if root.tag != "systemList":
            raise ValueError("Expected systemList in platform configuration")
        supplements: dict[str, dict[str, Any]] = {}
        allowed = {"name", "aliases", "base_platform", "variant", "badge_text", "theme_label"}
        for supplement in document["platforms"]:
            name = supplement["name"]
            if name in supplements or set(supplement) - allowed:
                raise ValueError("Duplicate or unsupported platform supplement: " + name)
            supplements[name] = supplement
        records: list[dict[str, Any]] = []
        for node in root.findall("system"):
            name = node.findtext("name") or ""
            rom_path = node.findtext("path") or ""
            if not rom_path.startswith("%ROMPATH%/"):
                raise ValueError("Platform ROM path must use %ROMPATH%/: " + name)
            records.append({
                "name": name,
                "fullname": node.findtext("fullname") or name,
                "rom_directory": rom_path[len("%ROMPATH%/"):],
                "theme": node.findtext("theme") or "",
                "platform": node.findtext("platform") or "",
                "extension": node.findtext("extension") or "",
                "commands": [
                    {"attributes": dict(command.attrib), "text": command.text or ""}
                    for command in node.findall("command")
                ],
                "xml": ET.tostring(node, encoding="unicode"),
                "aliases": [],
                "base_platform": None,
                "variant": None,
                "badge_text": None,
                "theme_label": None,
                **supplements.pop(name, {}),
            })
        if supplements:
            raise ValueError("Platform supplements absent from XML: " + ", ".join(supplements))
        registry = cls({"version": 1, "platforms": records})
        registry.config_dir = directory
        return registry

    def resolve(self, value: str) -> dict[str, Any] | None:
        matches = self.aliases.get(platform_key(value), set())
        if len(matches) > 1:
            raise ValueError(
                "Ambiguous platform {!r}: {}".format(value, ", ".join(sorted(matches)))
            )
        return self.records[next(iter(matches))] if matches else None

    def identify(self, *values: str) -> dict[str, Any] | None:
        """Prefer the real directory/name over generic collection or shortname hints."""
        for value in values:
            record = self.resolve(value)
            if record is not None:
                return record
        return None

    def is_hack(self, value: str) -> bool:
        record = self.resolve(value)
        return record is not None and record.get("variant") == "hack"

    @staticmethod
    def theme_rule(record: dict[str, Any]) -> dict[str, Any]:
        return {
            "name": record["name"],
            "theme": record["theme"],
            "source": record.get("base_platform") or record["theme"],
            "badge_text": record.get("badge_text"),
            "system_name": record.get("theme_label"),
        }

    @staticmethod
    def system_element(record: dict[str, Any]) -> ET.Element:
        """Return the XML definition with its original child order and extra fields."""
        return ET.fromstring(str(record["xml"]))
