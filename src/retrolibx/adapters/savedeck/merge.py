"""Merge native SaveDeck lists and protect the captured file baseline."""

import hashlib
from pathlib import Path

from retrolibx.core.models import Diagnostic
from retrolibx.core.operations import ExportIntent

from .document import merge_documents, parse_document, relative_path, render_document


def filter_missing_roms(data: dict, source_root: Path, diagnostics: list[Diagnostic]) -> dict:
    """Keep only existing ROM entries, including when retaining old custom entries."""
    games = []
    for game in data["games"]:
        path = source_root.joinpath(*relative_path(game["file"]).parts)
        if path.is_file():
            games.append(game)
        elif not any(item.code == "missing-rom" and item.path == path for item in diagnostics):
            diagnostics.append(Diagnostic(
                severity="warning", code="missing-rom",
                message=f"ROM 文件不存在，已从 SaveDeck 列表排除：{path}",
                path=path, game_name=game["name"]))
    return {**data, "games": games}


def merge_lists(intent: ExportIntent, target: Path, *, source_roots: dict[str, Path], replace: bool = False,
                valid_files: dict[str, set[str]] | None = None) -> None:
    for request in intent.texts:
        if request.destination.name != "savedeck.toml":
            continue
        path = target.joinpath(*request.destination.parts).resolve()
        path.relative_to(target.resolve())
        raw = path.read_bytes() if path.is_file() else None
        data = parse_document(request.content.encode("utf-8"))
        if raw is not None:
            data = merge_documents(parse_document(raw), data, replace=replace,
                                   valid_files=(valid_files or {}).get(request.destination.parent.as_posix()))
        data = filter_missing_roms(data, source_roots[request.destination.parent.as_posix()], intent.diagnostics)
        request.content = render_document(data)
        request.expected_sha256 = hashlib.sha256(raw).hexdigest() if raw is not None else ""
        request.backup = True
