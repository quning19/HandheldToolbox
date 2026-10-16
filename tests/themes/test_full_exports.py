"""Full local exports from the user's seven real themes, retaining artifacts."""
import json
import os
from pathlib import Path
import time

import pytest

from frontend_platforms.user_catalog import default_definitions
from theme_converter.service import import_original, local_themes, adapt_theme, capabilities_name
from theme_converter.state import source_index

ROOT = Path(__file__).resolve().parents[2]
THEMES = ("canvas-es-de", "aura-es-de", "alekfull-nx-es-de", "elementerial-es-de",
          "iconic-es-de", "iisu-interpreted-es-de", "playstation-x-es-de")


def session_directory():
    root = Path(os.environ["FTT_FUNCTIONAL_SESSION"]).resolve()
    if not root.is_relative_to((ROOT / "test_data").resolve()):
        raise ValueError("Functional test directory escaped test_data")
    return root


@pytest.mark.parametrize("folder", THEMES)
def test_complete_real_theme_import_and_export(folder):
    source = ROOT / "test_data/themes/original" / folder
    assert source.is_dir(), "缺少真实主题，不以跳过冒充通过"
    workspace = session_directory() / folder.removesuffix("-es-de") / "w"
    definitions = default_definitions()
    before = source_index(source)
    started = time.monotonic()

    def progress(text, value, _cancellable):
        print(f"[{folder}] {value}% {text}", flush=True)

    identity = import_original(workspace, source, progress=progress)
    info = next(item for item in local_themes(workspace, definitions) if item.id == identity)
    adapt_theme(workspace, definitions, info, lambda: False, progress)
    info = next(item for item in local_themes(workspace, definitions) if item.id == identity)
    assert info.converted and not info.stale, info.reason
    assert capabilities_name(info.output) == capabilities_name(source) + "_天马G"
    assert source_index(source) == before, "真实主题原版发生变化"
    records = json.loads((workspace / "config/theme-results.json").read_text(encoding="utf-8"))
    report = json.loads(Path(records[identity]["report"]).read_text(encoding="utf-8"))
    assert not report["errors"]
    assert len(report["platforms"]) == 12
    for platform in report["platforms"]:
        for edge in platform["edges"]:
            if edge["type"] in {"resource", "xml", "existing"}:
                assert (info.output / edge["target"]).is_file(), edge
    # Prove at least one inherited GBA HACK illustration actually went through
    # image processing, rather than merely checking a successful status flag.
    hack = next(item for item in report["platforms"] if item["id"] == "GBA HACK")
    artwork = [edge for edge in hack["edges"] if edge["type"] == "resource" and edge["role"] == "art"
               and Path(edge["target"]).suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}]
    assert artwork, "没有生成可检查的 GBA hack 平台插画"
    assert any((source / edge["source"]).read_bytes() != (info.output / edge["target"]).read_bytes() for edge in artwork)
    files = [path for path in info.output.rglob("*") if path.is_file()]
    summary = {"theme": info.name, "identity": identity, "output": str(info.output),
               "files": len(files), "bytes": sum(path.stat().st_size for path in files),
               "platforms": 12, "warnings": len(report["warnings"]),
               "seconds": round(time.monotonic() - started, 3)}
    (workspace.parent / "result.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
