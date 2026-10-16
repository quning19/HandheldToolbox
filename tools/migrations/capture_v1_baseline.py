"""Record the unchanged 2026-10-15 XML baseline for v1 user-config migration."""
import json
from pathlib import Path
from xml.etree import ElementTree as ET

root = Path(__file__).resolve().parents[2]
package = root / "src/frontend_platforms"
supplements = {r["name"]: r for r in json.loads((package / "platforms.json").read_text(encoding="utf-8"))["platforms"]}
rows = []
for node in ET.parse(package / "custom_systems-PG/es_systems.xml").getroot().findall("system"):
    identifier = node.findtext("name")
    info = supplements.get(identifier, {})
    directory = node.findtext("path")[len("%ROMPATH%/"):]
    rows.append(dict(id=identifier, name=info.get("theme_label") or directory, directory=directory,
                     parent=info.get("base_platform") or "", mode="separate" if info.get("base_platform") else "inherit",
                     badge=info.get("badge_text") or ""))
if not any(r["id"] == "pspminis" for r in rows):
    rows.append(dict(id="pspminis", name="PSP Minis", directory="PSP Minis", parent="psp", mode="inherit", badge=""))
(package / "baseline-v1.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
