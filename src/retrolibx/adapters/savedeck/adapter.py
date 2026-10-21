"""Render SaveDeck library editor 1.0.1 compatible lists and media intents."""

from __future__ import annotations

from pathlib import Path, PurePosixPath
import re
from uuid import uuid4

from retrolibx.adapters.base import DetectionResult, ImportResult, LibraryAdapter
from retrolibx.core.models import Capabilities, Diagnostic, Library
from retrolibx.core.operations import ExportIntent, FileRequest, TextRequest
from retrolibx.core.options import ConflictPolicy, ExportOptions, ImportOptions
from retrolibx.errors import ValidationError
from retrolibx.utils.discovery import rom_relative_path

from .document import relative_path, render_document
from ..pegasus.savedeck_policy import canonical_fields, command, extensions, value


def platform_directory(system) -> PurePosixPath:
    # Keep Pegasus bundle names and subdirectories; aliases are not output names.
    source = system.metadata.get("source_platform", "")
    return relative_path(system.metadata.get("export_directory")
                         or (source if source != "." else "")
                         or system.id)


def ordered_games(system):
    # Match the Pegasus adapter's sort-by/name fallback; Python sorting is stable.
    return sorted(system.games, key=lambda game: game.sort_name or game.name)


class SaveDeckAdapter(LibraryAdapter):
    name = "savedeck"
    aliases = ("save-deck",)
    capabilities = Capabilities(artwork=True, video=True, launch_config=True)

    @classmethod
    def detect(cls, path: Path) -> DetectionResult:
        return DetectionResult(format=cls.name, confidence=0, evidence=[])

    def import_library(self, path: Path, options: ImportOptions) -> ImportResult:
        raise ValidationError("SaveDeck 当前作为导出目标；请选择天马 G 或其他受支持的来源")

    def render_library(self, library: Library, target: Path, options: ExportOptions) -> ExportIntent:
        if options.conflict == ConflictPolicy.RENAME:
            raise ValidationError("SaveDeck 导出不支持重命名冲突文件，否则配置中的路径将失效")
        intent = ExportIntent()
        directories = set()
        for system in library.systems:
            directory = platform_directory(system)
            if directory.as_posix().casefold() in directories:
                raise ValidationError(f"SaveDeck 平台输出目录重复：{directory}")
            directories.add(directory.as_posix().casefold())
            collection = canonical_fields(system.metadata.get("pegasus", {}))
            data = {"format_version": 1, "platform": (collection.get("collection") or [system.name])[-1], "games": []}
            default_launch = command(value(collection, "launch"))
            if default_launch:
                data["launch"] = default_launch
            data.update(extensions(collection, {"collection", "sort-by", "launch"}))
            media_destinations = {}
            for game in ordered_games(system):
                if not game.roms:
                    raise ValidationError(f"游戏没有 ROM 入口：{game.name}")
                # Use the same file-presence snapshot for naming and entry selection.
                rom_entries = [(rom, rom.path.is_file()) for rom in game.roms]
                existing_count = game.source_metadata.get("valid_rom_count", sum(exists for _, exists in rom_entries))
                original = canonical_fields(game.source_metadata.get("pegasus_fields", {}))
                for rom, exists in rom_entries:
                    relative = relative_path(rom_relative_path(rom.path, rom.metadata).as_posix())
                    root = Path(system.metadata.get("source_root") or rom.path.resolve().parents[len(relative.parts) - 1]).resolve()
                    if not rom.path.resolve().is_relative_to(root):
                        raise ValidationError(f"ROM 不在平台目录内：{rom.path}")
                    relative = relative_path(rom.path.resolve().relative_to(root).as_posix())
                    if not exists:
                        intent.diagnostics.append(Diagnostic(
                            severity="warning", code="missing-rom",
                            message=f"ROM 文件不存在，已从 SaveDeck 列表排除：{rom.path}",
                            path=rom.path, game_name=game.name))
                        continue
                    name = game.name if existing_count == 1 else f"{game.name} · {relative.stem}"
                    entry = {"name": name, "file": relative.as_posix(),
                             "id": rom.metadata.get("savedeck", {}).get("id") or str(uuid4()),
                             "sort": f"{len(data['games']) + 1:06d}"}
                    if game.description:
                        entry["description"] = game.description
                    launch = command(value(original, "launch")) if original else command(game.launch.command or "") if game.launch else ""
                    if launch:
                        entry["launch"] = launch
                    entry.update(extensions(original, {"game", "files", "sort-by", "description", "launch"}))
                    # Multiple Pegasus file entries become separate SaveDeck launch entries.
                    for key, media in (("cover", game.media.box_front), ("video", game.media.video)):
                        if media is None:
                            continue
                        if not media.resolve().is_relative_to(root):
                            raise ValidationError(f"SaveDeck 无法共用平台目录外的媒体：{media}")
                        if not media.is_file():
                            intent.diagnostics.append(Diagnostic(severity="warning", code="missing-media",
                                                                 message=f"{game.name}: {media}", path=media))
                            continue
                        folder = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).rstrip(" .")
                        if not folder or folder in {".", ".."}:
                            raise ValidationError(f"SaveDeck 媒体目录名无效：{name}")
                        asset = relative_path((PurePosixPath("media") / folder / (key + media.suffix.lower())).as_posix())
                        destination = directory / asset
                        identity = destination.as_posix().casefold()
                        if identity in media_destinations and media_destinations[identity] != media.resolve():
                            raise ValidationError(f"SaveDeck 媒体目标重复：{destination}")
                        if identity not in media_destinations:
                            intent.files.append(FileRequest(source=media, destination=destination, category="media"))
                            media_destinations[identity] = media.resolve()
                        entry[key] = asset.as_posix()
                    data["games"].append(entry)
            intent.texts.append(TextRequest(destination=directory / "savedeck.toml", content=render_document(data)))
        return intent
