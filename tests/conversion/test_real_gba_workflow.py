"""Actual provided GBA excerpt: initial conversion, skip, then two added ROMs."""
import json
from pathlib import Path
import shutil

from library_converter.desktop import scan_library, convert_library
from frontend_platforms.user_catalog import default_definitions
from retrolibx.adapters.esde.merge import parse_xml
from theme_converter.state import source_index
from tests.themes.test_full_exports import ROOT, session_directory


def test_real_gba_initial_increment_and_two_added_roms():
    original = ROOT / "test_data/library/real-gba-demo-20261015"
    case = session_directory() / "gba"
    source, workspace = case / "roms", case / "w"
    shutil.copytree(original / "ROMs", source)
    before = source_index(original / "ROMs")
    definitions = default_definitions()
    progress = lambda text, value, *_: print(f"[GBA] {value}% {text}", flush=True)

    def scan():
        result = scan_library(workspace, definitions, str(source), None, lambda: False, progress, lambda _item: None)
        assert not any(info.error for info in result.platforms.values()), {key: value.error for key, value in result.platforms.items()}
        return result

    session = scan()
    initial = {name: info.roms for name, info in session.platforms.items()}
    assert initial == {"GBA": 8, "GBA hack": 8, "GBA vib": 4}
    selected = list(session.platforms)
    first = convert_library(session, selected, False, False, workspace, lambda: False, progress)
    assert first["roms"] == 20
    target = Path(first["output"])
    for name in ("es_systems.xml", "es_find_rules.xml", "es_import_rules.xml", "es_systems_sorting.xml"):
        assert (target / "custom_systems" / name).is_file()
    media = {path.relative_to(target).as_posix(): (path.stat().st_size, path.stat().st_mtime_ns)
             for path in (target / "downloaded_media").rglob("*") if path.is_file()}
    session = scan()
    assert sum(info.existing for info in session.platforms.values()) == 20
    second = convert_library(session, selected, False, False, workspace, lambda: False, progress)
    assert second["roms"] == 0
    assert media == {path.relative_to(target).as_posix(): (path.stat().st_size, path.stat().st_mtime_ns)
                     for path in (target / "downloaded_media").rglob("*") if path.is_file()}
    shutil.copytree(original / "add-later", source, dirs_exist_ok=True)
    session = scan()
    assert sum(info.roms for info in session.platforms.values()) == 22
    assert sum(info.existing for info in session.platforms.values()) == 20
    third = convert_library(session, selected, False, False, workspace, lambda: False, progress)
    assert third["roms"] == 2
    gamelists = list((target / "gamelists").rglob("gamelist.xml"))
    assert len(gamelists) == 3
    assert sum(len(parse_xml(path.read_bytes(), "gameList").findall("game")) for path in gamelists) == 22
    assert source_index(original / "ROMs") == before
    result = {"original_archive": json.loads((original / "manifest.json").read_text(encoding="utf-8"))["source_archive"],
              "initial_platforms": initial, "first_selected": first["roms"], "repeat_selected": second["roms"],
              "added_selected": third["roms"], "final_games": 22, "output": str(target)}
    (case / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
