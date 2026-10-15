"""Build an inspectable Android task through IR, adapter, planner and executor."""

import base64
import hashlib
import json
import re
from copy import deepcopy
from typing import Literal
from pathlib import Path, PurePosixPath

from lxml import etree
from pydantic import BaseModel, ConfigDict, Field

from frontend_platforms import platform_component, platform_configuration
from retrolibx.adapters.esde.merge import merge_gamelists, parse_xml, xml_text
from retrolibx.core.android import android_intent_command, android_path, render_android_script
from retrolibx.core.executor import PlanExecutor
from retrolibx.core.models import Library, System
from retrolibx.core.operations import ExportIntent, TextRequest
from retrolibx.core.options import ExportOptions, ImportOptions, RomMode
from retrolibx.core.source_profiles import SourceProfile
from retrolibx.errors import ValidationError
from retrolibx.utils.encoding import detect_metadata_encoding

from .service import ConversionService
from .shared_media import prepare_shared_media
from .selection import select_entries


class HandheldConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_root: Path
    device_rom_root: str
    esde_root: str
    platform_config_dir: Path | None = None
    source_profile: Path | None = None
    systems_template: Path | None = None
    target_snapshot: Path | None = None
    target_empty: bool = False
    encoding: str = "utf-8-sig"
    launch_overrides: dict[str, str] = Field(default_factory=dict)
    metadata_launch_systems: list[str] = Field(default_factory=list)
    system_templates: dict[str, str] = Field(default_factory=dict)
    confirmed_systems: list[str] = Field(default_factory=list)
    device_index: Path | None = None
    media_root: str | None = None
    system_ids: dict[str, str] = Field(default_factory=dict)
    shared_pegasus: bool = False
    gamelist_rom_roots: dict[str, list[str]] = Field(default_factory=dict)
    gamelist_sources: dict[str, str] = Field(default_factory=dict)
    existing_entries: Literal["merge", "skip", "replace"] = "merge"
    existing_roms_only: bool = False
    media_path_aliases: dict[str, dict[str, Path]] = Field(default_factory=dict)
    device_media_sources: dict[str, str] = Field(default_factory=dict)
    versioned_backups: bool = False

    @classmethod
    def load(cls, path: Path) -> "HandheldConfig":
        try:
            config = cls.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise ValidationError(f"Invalid handheld configuration: {exc}") from exc
        for name in (
            "source_root", "systems_template", "target_snapshot", "device_index",
            "platform_config_dir", "source_profile"
        ):
            value = getattr(config, name)
            if value is not None:
                setattr(config, name, (path.parent / value).resolve())
        android_path(config.device_rom_root)
        android_path(config.esde_root)
        for aliases in config.gamelist_rom_roots.values():
            for alias in aliases:
                android_path(alias)
        for aliases in config.media_path_aliases.values():
            for reference, local in aliases.items():
                aliases[reference] = (path.parent / local).resolve()
        for target, source in (*config.gamelist_sources.items(), *config.system_templates.items()):
            platform_component(target)
            platform_component(source)
        return config


def scan_handheld(config: HandheldConfig) -> Library:
    profile_path = config.source_profile or (
        Path(__file__).parents[1] / "profiles/pegasus-g.json"
    )
    return ConversionService(platform_config_dir=config.platform_config_dir).import_library(
        config.source_root, "pegasus",
        ImportOptions(metadata_encoding=config.encoding, source_profile=profile_path,
                      media_path_aliases=config.media_path_aliases),
    )[1]


def _media_location(config: HandheldConfig) -> tuple[str, dict[str, str]]:
    default = str(android_path(config.esde_root) / "downloaded_media")
    actual = default
    checks: dict[str, str] = {}
    settings = (
        config.target_snapshot / "settings/es_settings.xml" if config.target_snapshot else None
    )
    if settings is not None and not settings.is_file():
        settings = config.target_snapshot / "es_settings.xml" if config.target_snapshot else None
    if settings and settings.is_file():
        raw = settings.read_bytes()
        try:
            settings_root = parse_xml(raw, "config")
        except ValidationError:
            # ES-DE's native settings are XML siblings, not necessarily one root.
            fragment = re.sub(rb"^\s*(?:\xef\xbb\xbf)?<\?xml[^?]*\?>", b"", raw, count=1)
            settings_root = parse_xml(b"<config>" + fragment + b"</config>", "config")
        node = settings_root.find("string[@name='MediaDirectory']")
        value = node.get("value", "") if node is not None else ""
        if value:
            actual = str(android_path(value))
        relative = (
            settings.relative_to(config.target_snapshot).as_posix()
            if config.target_snapshot
            else "es_settings.xml"
        )
        checks[str(android_path(config.esde_root) / relative)] = hashlib.sha256(raw).hexdigest()
    if config.media_root and str(android_path(config.media_root)) != actual:
        raise ValidationError("media_root does not match the captured ES-DE MediaDirectory")
    return actual, checks


def _target_name(system: System) -> str:
    try:
        return platform_component(system.metadata.get("target_system", system.id))
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc


def _system_node(root: etree._Element, name: str) -> etree._Element | None:
    return next((node for node in root.findall("system") if node.findtext("name") == name), None)


def _systems_xml(config: HandheldConfig, library: Library, baseline: bytes | None) -> str:
    configuration = platform_configuration(config.platform_config_dir)
    template = parse_xml(configuration["es_systems.xml"].encode("utf-8"), "systemList")
    if config.systems_template is not None:
        try:
            overrides = parse_xml(config.systems_template.read_bytes(), "systemList")
        except OSError as exc:
            raise ValidationError(
                f"Cannot read system template: {config.systems_template}"
            ) from exc
        for node in overrides.findall("system"):
            old = _system_node(template, node.findtext("name") or "")
            if old is not None:
                template.replace(old, deepcopy(node))
            else:
                template.append(deepcopy(node))
    root = parse_xml(baseline, "systemList") if baseline is not None else deepcopy(template)
    baseline_names = {node.findtext("name") for node in root.findall("system")} if baseline else set()
    for node in template.findall("system"):
        if _system_node(root, node.findtext("name") or "") is None:
            root.append(deepcopy(node))
    registry = ConversionService(platform_config_dir=config.platform_config_dir).adapters.systems
    selected_paths: list[PurePosixPath] = []
    selected_ids = {_target_name(system) for system in library.systems}
    for system in library.systems:
        record = registry.records.get(system.id)
        target_name = _target_name(system)
        existing_system = _system_node(root, target_name)
        explicit_template = config.system_templates.get(system.id) or config.system_templates.get(target_name)
        template_id = explicit_template or system.metadata.get("template_system") or (
            record.base_system or record.id if record else system.id
        )
        source = _system_node(root, template_id) if explicit_template else _system_node(template, system.id)
        if source is None:
            source = _system_node(template, template_id)
        if source is None and system.metadata.get("reused_system"):
            source = existing_system
        if source is None:
            raise ValidationError(f"Missing Android system template: {system.id}")
        base_template = source
        if explicit_template:
            default_template = _system_node(template, template_id)
            if default_template is not None:
                base_template = default_template
        if target_name != system.id and system.id not in baseline_names:
            # A deliberate output alias replaces the default entry, not its ROM category.
            old = _system_node(root, system.id)
            if old is not None:
                root.remove(old)
        if system.metadata.get("reused_system") and existing_system is not None:
            source = existing_system
        node = deepcopy(source)
        for child in base_template:
            if not isinstance(child.tag, str):
                continue
            if node.find(child.tag) is None:
                node.append(deepcopy(child))
        rom_root = android_path(config.device_rom_root) / system.metadata["source_platform"]
        if any(rom_root.is_relative_to(p) or p.is_relative_to(rom_root) for p in selected_paths):
            raise ValidationError(f"Overlapping system ROM roots: {rom_root}")
        selected_paths.append(rom_root)
        for old in root.findall("system"):
            if old.findtext("name") in selected_ids:
                continue
            old_path = (old.findtext("path") or "").replace("%ROMPATH%", config.device_rom_root)
            if old_path.startswith("/"):
                old_root = PurePosixPath(old_path)
                if rom_root.is_relative_to(old_root) or old_root.is_relative_to(rom_root):
                    raise ValidationError(
                        f"Existing system scans selected ROM root: {old.findtext('name')}"
                    )
        values = [("name", target_name), ("fullname", system.name), ("path", str(rom_root))]
        if system.metadata.get("reused_system"):
            values[-1] = ("path", node.findtext("path") or str(rom_root))
        if record and record.definition and not system.metadata.get("reused_system"):
            values.extend((tag, record.definition[tag]) for tag in ("theme", "platform"))
        for tag, value in values:
            if tag == "fullname" and system.metadata.get("reused_system") and node.findtext(tag):
                continue
            child = node.find(tag)
            if child is None:
                child = etree.SubElement(node, tag)
            child.text = value
        override = config.launch_overrides.get(system.id) or config.launch_overrides.get(
            target_name
        )
        if {system.id, target_name}.intersection(config.metadata_launch_systems):
            if override:
                raise ValidationError(f"Choose metadata launch or launch_overrides, not both: {target_name}")
            launch = system.metadata.get("pegasus", {}).get("launch", [])
            override = android_intent_command(launch[-1] if launch else "")
        commands = node.findall("command")
        if override and not (len(commands) == 1 and commands[0].text == override):
            first = node.index(node.find("command")) if node.find("command") is not None else len(node)
            for command in commands:
                node.remove(command)
            command = etree.Element("command")
            command.text = override
            node.insert(first, command)
        if not node.findall("command") or any(
            not command.text or "PLACEHOLDER" in command.text or "%ROM" not in command.text
            for command in node.findall("command")
        ):
            raise ValidationError(f"Invalid launch template: {system.id}")
        if existing_system is not None:
            root.replace(existing_system, node)
        else:
            root.append(node)
    return xml_text(root)


def _launch_errors(config: HandheldConfig, library: Library) -> list[str]:
    errors: list[str] = []
    profile = SourceProfile.model_validate(library.metadata["source_profile"])
    for system in library.systems:
        target_name = _target_name(system)
        if (
            system.id in profile.confirmation_systems
            and not {system.id, target_name}.intersection(config.confirmed_systems + config.metadata_launch_systems)
        ):
            errors.append(f"{system.id}: source profile requires explicit launch confirmation")
    return errors


def _reuse_systems(config: HandheldConfig, library: Library, snapshot: Path) -> None:
    existing = snapshot / "custom_systems/es_systems.xml"
    if not existing.is_file():
        return
    root = parse_xml(existing.read_bytes(), "systemList")
    registry = ConversionService(platform_config_dir=config.platform_config_dir).adapters.systems
    for system in library.systems:
        wanted = str(android_path(config.device_rom_root) / system.metadata["source_platform"])
        matches = [
            node
            for node in root.findall("system")
            if (node.findtext("path") or "")
            .replace("%ROMPATH%", config.device_rom_root)
            .rstrip("/")
            == wanted
        ]
        if len(matches) > 1:
            raise ValidationError(f"Multiple existing systems match source ROM root: {wanted}")
        if matches:
            name = matches[0].findtext("name") or ""
            try:
                platform_component(name)
            except ValueError as exc:
                raise ValidationError(str(exc)) from exc
            record = registry.records.get(system.id)
            system.metadata.setdefault(
                "template_system", (record.base_system or record.id if record else system.id)
            )
            system.metadata["reused_system"] = True
            system.metadata["target_system"] = name


def build_handheld(config: HandheldConfig, platforms: list[str], output: Path) -> dict[str, object]:
    if not platforms:
        raise ValidationError("Select at least one --platform")
    if output.exists() and any(output.iterdir()):
        raise ValidationError("Task directory must be empty; use a new --out")
    source_root = config.source_root.resolve()
    if output.resolve().is_relative_to(source_root):
        raise ValidationError("Task directory cannot be inside source ROMs")
    service = ConversionService(platform_config_dir=config.platform_config_dir)
    configuration = platform_configuration(service.adapters.systems.platform_config_dir)
    _, library = service.import_library(
        source_root,
        "pegasus",
        ImportOptions(
            platforms=platforms, metadata_encoding=config.encoding,
            media_path_aliases=config.media_path_aliases,
            source_profile=config.source_profile or (
                Path(__file__).parents[1] / "profiles/pegasus-g.json"
            ),
        ),
    )
    adapter = service.adapters.resolve("es-de")
    options = ExportOptions(
        rom_mode=RomMode.NONE, shared_pegasus=config.shared_pegasus,
        conflict="overwrite" if config.existing_entries == "replace" else "skip",
    )
    snapshot = config.target_snapshot or output.parent / ".empty-esde-snapshot"
    for system in library.systems:
        mapped = config.system_ids.get(system.id)
        if mapped:
            try:
                platform_component(mapped)
            except ValueError as exc:
                raise ValidationError(str(exc)) from exc
            record = service.adapters.systems.records.get(system.id)
            system.metadata["template_system"] = (
                record.base_system or record.id if record else system.id
            )
            system.metadata["target_system"] = mapped
    _reuse_systems(config, library, snapshot)
    selection = None
    if config.existing_entries != "merge" or config.existing_roms_only:
        selection = select_entries(library, snapshot, {
            _target_name(system): str(android_path(config.device_rom_root) / system.metadata["source_platform"])
            for system in library.systems
        }, policy=config.existing_entries, existing_only=config.existing_roms_only)
    intent = adapter.render_library(library, snapshot, options)
    errors = [d.message for d in library.diagnostics if d.severity == "error"]
    errors.extend(_launch_errors(config, library))
    if config.target_snapshot is None and not config.target_empty:
        errors.append("Provide target_snapshot or explicitly set target_empty")
    if config.target_snapshot is not None and not config.target_snapshot.is_dir():
        errors.append("Target snapshot directory is missing")
    merge_gamelists(intent, snapshot, {
        _target_name(system): str(
            android_path(config.device_rom_root) / system.metadata["source_platform"]
        )
        for system in library.systems
    }, config.gamelist_rom_roots, config.gamelist_sources)
    systems_path = PurePosixPath("custom_systems/es_systems.xml")
    existing_path = snapshot.joinpath(*systems_path.parts)
    baseline = existing_path.read_bytes() if existing_path.is_file() else None
    try:
        content = _systems_xml(config, library, baseline)
    except ValidationError as exc:
        errors.append(str(exc))
        # Keep a complete reference preview; the errors prohibit emitting apply.sh.
        content = configuration["es_systems.xml"]
    intent.texts.append(
        TextRequest(
            destination=systems_path,
            content=content,
            expected_sha256=hashlib.sha256(baseline).hexdigest() if baseline is not None else "",
            backup=True,
        )
    )
    for name, default_content in configuration.items():
        if name == "es_systems.xml":
            continue
        destination = PurePosixPath("custom_systems") / name
        old_path = snapshot.joinpath(*destination.parts)
        old_bytes = old_path.read_bytes() if old_path.is_file() else None
        intent.texts.append(
            TextRequest(
                destination=destination,
                content=old_bytes.decode("utf-8") if old_bytes is not None else default_content,
                expected_sha256=hashlib.sha256(old_bytes).hexdigest() if old_bytes is not None else "",
                backup=True,
            )
        )
    if config.shared_pegasus:
        media_base, _ = _media_location(config)
        prepare_shared_media(
            library, intent, source_root, media_base, config.encoding,
            device_index=config.device_index is not None,
            retained_sources={source_root / name for name in config.device_media_sources},
        )
    sizes: dict[str, int] = {}
    if config.device_index:
        sizes = json.loads(config.device_index.read_text(encoding="utf-8"))["sizes"]
    summary: dict[str, object] = {
        "platforms": sorted(set(platforms)),
        "games": library.game_count,
        "roms": sum(len(g.roms) for s in library.systems for g in s.games),
        "media_targets": len(intent.files),
        "shared_pegasus": config.shared_pegasus,
        "source_metadata_updates": len(intent.source_metadata_updates),
        "source_media_cleanup": sum(request.cleanup for request in intent.media_relocations),
        "shared_media_checks": len(intent.media_relocations),
        "media_bytes": sum(
            sizes.get(f.source.relative_to(source_root).as_posix(), f.source.stat().st_size)
            for f in intent.files
        ),
        "issues": [d.model_dump(mode="json") for d in library.diagnostics + intent.diagnostics],
        "errors": errors,
        "executable": not errors,
        "selection": selection,
    }
    report = (
        "# Conversion preview\n\n"
        + "\n".join(f"- {key}: {value}" for key, value in summary.items())
        + "\n"
    )
    bundle = ExportIntent(
        texts=[
            TextRequest(destination=PurePosixPath("preview.md"), content=report),
            TextRequest(
                destination=PurePosixPath("summary.json"),
                content=json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
            ),
        ]
    )
    # One payload map supplies both previews and the publication manifest.
    payload = {"files/" + request.destination.as_posix(): request.content for request in intent.texts}
    for request in intent.source_metadata_updates:
        relative = request.source.relative_to(source_root).as_posix()
        payload["files/source-metadata/" + relative + ".b64"] = request.content_base64 + "\n"
        raw_metadata = base64.b64decode(request.content_base64)
        payload["preview/source-metadata/" + relative + ".preview.txt"] = raw_metadata.decode(
            detect_metadata_encoding(raw_metadata) if config.encoding == "auto" else config.encoding)
    if not errors:
        media_root, config_checks = _media_location(config)
        plan = service.planner.plan(
            intent,
            source_root=source_root,
            target_root=snapshot,
            source_format="pegasus",
            target_format="es-de",
            options=options,
        )
        script, publication_payload = render_android_script(
            plan,
            config.device_rom_root,
            config.esde_root,
            [rom.path for s in library.systems for g in s.games for rom in g.roms],
            sizes,
            media_root,
            config_checks,
            config.device_media_sources,
            config.versioned_backups,
        )
        payload.update(publication_payload)
        payload["apply.sh"] = script
        payload["plan.json"] = plan.model_dump_json(indent=2) + "\n"
    bundle.texts.extend(TextRequest(destination=PurePosixPath(destination), content=text)
                        for destination, text in payload.items())
    plan = service.planner.plan(
        bundle,
        source_root=source_root,
        target_root=output,
        source_format="pegasus",
        target_format="android-task",
        options=options,
    )
    PlanExecutor().execute(plan)
    return summary
