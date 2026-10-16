"""Copy approved legacy inputs and development tools out of the immutable archive."""
from pathlib import Path
import json
import shutil
from datetime import datetime

ROOT = Path(__file__).resolve().parents[2]
OLD = ROOT / "archive/FrontendThemeConverter-20261016"
MAPPINGS = {
    "source/themes": "test_data/themes/original",
    "source/sample": "test_data/themes/reference",
    "source/configs": "test_data/themes/legacy-configs",
    "dist": "artifacts/themes/legacy",
    "lab": "research/themes/legacy-lab",
    "config": "tools/themes/config",
    "tools": "tools/themes",
    "docs": "docs/archive/frontend-theme-converter",
}
for old, new in MAPPINGS.items():
    shutil.copytree(OLD / old, ROOT / new, dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
for name in ("README.md", "TODO.md", "requirements.txt", "fix_esde_artbook.sh"):
    shutil.copy2(OLD / name, ROOT / "docs/archive/frontend-theme-converter" / name)
shutil.copy2(OLD / "tests/test_batches.py", ROOT / "tests/themes/test_legacy_batches.py")
project_path = ROOT / "tools/themes/config/project.json"
project = json.loads(project_path.read_text(encoding="utf-8"))
project["paths"].update(system_config="src/frontend_platforms/custom_systems-PG/es_systems.xml",
    reference_system_config="test_data/themes/legacy-configs/custom_systems-es-de/es_systems.xml",
    themes="artifacts/themes/development", reports="artifacts/themes/reports",
    lab="research/themes/legacy-lab", platform_config="src/frontend_platforms/platforms.json")
project["theme_profiles"] = {key: "tools/themes/" + value for key, value in project["theme_profiles"].items()}
project_path.write_text(json.dumps(project, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
for path in (ROOT / "tools/themes/config/themes").glob("*.json"):
    profile = json.loads(path.read_text(encoding="utf-8"))
    for field in ("source_theme", "reference_theme", "staged"):
        if field in profile:
            for before, after in (("source/themes", "test_data/themes/original"), ("source/sample", "test_data/themes/reference"), ("dist/staged", "artifacts/themes/staged")):
                profile[field] = profile[field].replace(before, after)
    path.write_text(json.dumps(profile, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
common = ROOT / "tools/themes/common.py"
text = common.read_text(encoding="utf-8").replace('BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))', 'BASE = str(Path(__file__).resolve().parents[2])\nsys.path.insert(0, str(Path(BASE) / "src"))')
text = text.replace('"config/project.json"', '"tools/themes/config/project.json"').replace('"config/batches/%s.json"', '"tools/themes/config/batches/%s.json"')
common.write_text(text, encoding="utf-8")
test = ROOT / "tests/themes/test_legacy_batches.py"
text = test.read_text(encoding="utf-8").replace('parents[1]', 'parents[2]').replace('ROOT / "tools"', 'ROOT / "tools/themes"').replace('"config/', '"tools/themes/config/')
test.write_text(text, encoding="utf-8")
samples = ROOT / "workspace/temp/real-gba-demo-20261015"
sample_target = ROOT / "test_data/library/real-gba-demo-20261015"
if samples.exists():
    sample_target.parent.mkdir(parents=True, exist_ok=True)
    if sample_target.exists():
        raise FileExistsError(sample_target)
    samples.rename(sample_target)
manifest = dict(date=datetime.now().isoformat(), archived_project=str(OLD), mappings=MAPPINGS,
    real_gba_sample=str(sample_target.relative_to(ROOT)), note="Archive retained intact. No validation scripts, tests or device operations executed.")
(ROOT / "docs/archive/frontend-theme-converter/MIGRATION.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
