"""Versioned system mapping database."""

from __future__ import annotations

from collections import Counter
from importlib.resources import files
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

from frontend_platforms import PlatformRegistry, platform_key
from retrolibx.errors import MappingError


class PlatformMapping(BaseModel):
    playlist: list[str] = Field(default_factory=list)
    directory: list[str] = Field(default_factory=list)
    shortname: list[str] = Field(default_factory=list)


class SystemRecord(BaseModel):
    id: str
    name: str
    short_name: str | None = None
    base_system: str | None = None
    rom_directory: str | None = None
    theme: str | None = None
    definition: dict[str, Any] = Field(default_factory=dict)
    aliases: list[str] = Field(default_factory=list)
    extensions: list[str] = Field(default_factory=list)
    platforms: dict[str, PlatformMapping] = Field(default_factory=dict)


class RegistryDocument(BaseModel):
    version: int
    systems: dict[str, dict[str, object]]


class SystemRegistry:
    def __init__(
        self, records: dict[str, SystemRecord], version: int = 1,
        platform_config_dir: Path | None = None,
    ) -> None:
        self.records = records
        self.version = version
        self.platform_config_dir = platform_config_dir
        self._aliases: dict[str, set[str]] = {}
        display_names = Counter(record.name for record in records.values())
        for system_id, record in records.items():
            values = [system_id, *(record.aliases)]
            if display_names[record.name] == 1:
                values.append(record.name)
            for mapping in record.platforms.values():
                values.extend(mapping.playlist + mapping.directory + mapping.shortname)
            for value in values:
                self._aliases.setdefault(platform_key(value), set()).add(system_id)

    @classmethod
    def load(
        cls, path: Path | None = None, *, platform_config_dir: Path | None = None
    ) -> SystemRegistry:
        resource = path or Path(str(files("retrolibx.registry").joinpath("systems.yaml")))
        raw = yaml.safe_load(resource.read_text(encoding="utf-8"))
        document = RegistryDocument.model_validate(raw)
        records = {
            system_id: SystemRecord.model_validate({"id": system_id, **data})
            for system_id, data in document.systems.items()
        }
        if path is None:
            try:
                project = PlatformRegistry.load(config_dir=platform_config_dir)
            except (OSError, ValueError) as exc:
                raise MappingError("Cannot load shared platform configuration: " + str(exc)) from exc
            platform_config_dir = project.config_dir
            # The tested theme definitions are authoritative for internal identity.
            inherited = {
                resolved["name"]: record
                for record in records.values()
                if (resolved := project.resolve(record.id)) is not None
            }
            records = {
                name: record for name, record in records.items() if project.resolve(name) is None
            }
            for name, definition in project.records.items():
                old = inherited.get(name)
                mappings = dict(old.platforms) if old else {}
                mappings["es-de"] = PlatformMapping(directory=[definition["rom_directory"]])
                mappings["pegasus"] = PlatformMapping(shortname=[name])
                records[name] = SystemRecord(
                    id=name,
                    name=definition["fullname"],
                    base_system=definition.get("base_platform"),
                    rom_directory=definition["rom_directory"],
                    theme=definition["theme"],
                    definition=definition,
                    aliases=definition["aliases"]
                    + [definition["rom_directory"], definition["theme"]],
                    extensions=sorted(
                        {ext.lstrip(".").lower() for ext in definition["extension"].split()}
                    ),
                    platforms=mappings,
                )
        return cls(records, document.version, platform_config_dir)

    def resolve(self, value: str) -> SystemRecord | None:
        matches = self._aliases.get(platform_key(value), set())
        if len(matches) > 1:
            raise MappingError(f"Ambiguous system alias {value!r}: {', '.join(sorted(matches))}")
        return self.records[next(iter(matches))] if matches else None

    def directory(self, system_id: str, platform: str) -> str | None:
        record = self.records.get(system_id)
        if not record:
            return None
        mapping = record.platforms.get(platform)
        return mapping.directory[0] if mapping and mapping.directory else None
