"""Source-checkout launcher: python run_tool.py library|theme|gui|engine ..."""
from pathlib import Path
import runpy
import sys

TOOLS = {"library": "library_converter", "theme": "theme_converter", "gui": "frontend_gui", "engine": "retrolibx.cli"}
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
if len(sys.argv) < 2 or sys.argv[1] not in TOOLS:
    raise SystemExit("Usage: python run_tool.py library|theme|gui|engine [arguments]")
module = TOOLS[sys.argv.pop(1)]
runpy.run_module(module, run_name="__main__", alter_sys=True)
