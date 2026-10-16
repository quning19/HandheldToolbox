"""Add original attribution text and relocate the legacy preview source references."""
from pathlib import Path
import json
ROOT = Path(__file__).resolve().parents[2]
resources = ROOT / "src/frontend_gui/assets/cards"
index_path = resources / "index.json"
index = json.loads(index_path.read_text(encoding="utf-8"))
for style, record in index.items():
    source = ROOT / "test_data/themes/original" / record["source_theme"]
    notice = "Source theme: " + str(source.relative_to(ROOT)) + "\n\n"
    readme = source / "README.md"
    if readme.is_file():
        notice += readme.read_text(encoding="utf-8", errors="replace")
    (resources / style / "SOURCE-NOTICE.txt").write_text(notice, encoding="utf-8")
    for asset in record["assets"].values():
        asset["source"] = asset["source"].replace("src/frontend_gui/assets/platforms/", "docs/design/assets/legacy-platforms/")
index_path.write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
