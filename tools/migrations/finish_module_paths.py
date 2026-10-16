"""One-time source edits for the approved package relocation; not a test."""
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[2]
desktop = ROOT / "src/library_converter/desktop.py"
text = desktop.read_text(encoding="utf-8")
start = text.index("class Cancelled(Exception):")
end = text.index("def local_target", start)
text = text[:start] + "from frontend_common.jobs import Cancelled, checkpoint, new_job\n\n\n" + text[end:]
text = text.replace('Path(__file__).parents[1] / "profiles/pegasus-g.json"', 'Path(__file__).parents[1] / "retrolibx/profiles/pegasus-g.json"')
text = text.replace('            art_dir = Path(__file__).parents[1] / "gui/assets/platforms"\n            if not (art_dir / (info.art + ".webp")).is_file():\n                info.art = (art_record.theme if art_record else "") or ""', '            info.parent_art = (art_record.theme if art_record else "") or ""')
text = text.replace('    error: str = ""', '    error: str = ""\n    parent_art: str = ""')
desktop.write_text(text, encoding="utf-8")
p = ROOT / "src/library_converter/handheld.py"
p.write_text(p.read_text(encoding="utf-8").replace('Path(__file__).parents[1] / "profiles/pegasus-g.json"', 'Path(__file__).parents[1] / "retrolibx/profiles/pegasus-g.json"'), encoding="utf-8")
p = ROOT / "src/frontend_gui/tasks.py"
p.write_text(p.read_text(encoding="utf-8").replace("from library_converter.desktop import Cancelled", "from frontend_common.jobs import Cancelled"), encoding="utf-8")
p = ROOT / "src/frontend_platforms/platforms.json"
data = json.loads(p.read_text(encoding="utf-8"))
data["system_config_dir"] = "custom_systems-PG"
data["_comment"] = "完整平台定义维护于同包 custom_systems-PG 四个 XML；本文件仅维护别名、母体、类型和角标，不依赖外部项目。"
p.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
p = ROOT / "launch_gui.py"
p.write_text(p.read_text(encoding="utf-8").replace(' / "retrolibx" / "src"', ' / "src"').replace("retrolibx.gui.app", "frontend_gui.app"), encoding="utf-8")
p = ROOT / "pyproject.toml"
text = p.read_text(encoding="utf-8").replace('frontend-trans-tool = "retrolibx.gui.app:run"', 'frontend-trans-tool = "frontend_gui.app:run"\nlibrary-converter = "library_converter.__main__:main"\ntheme-converter = "theme_converter.__main__:main"')
text = text.replace('packages = ["src/retrolibx", "src/frontend_platforms"]', 'packages = ["src/retrolibx", "src/frontend_platforms", "src/frontend_devices", "src/frontend_common", "src/library_converter", "src/theme_converter", "src/frontend_gui"]')
text = text.replace('  "rich>=13.9",', '  "rich>=13.9",\n  "Pillow>=10",')
text = text.replace('  "Pillow>=10; sys_platform == \'win32\'",\n', '')
p.write_text(text, encoding="utf-8")
