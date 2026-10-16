"""Update maintained documentation links after relocation; historical snapshots stay literal."""
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
for path in [ROOT / "README.md", * (ROOT / "docs").glob("*.md"), *(ROOT / "docs/engine").glob("*.md")]:
    text = path.read_text(encoding="utf-8")
    text = text.replace("retrolibx/src/retrolibx/application/desktop.py", "src/library_converter/desktop.py")
    replacements = {
        "retrolibx/src/retrolibx/application/themes.py": "src/theme_converter/service.py",
        "retrolibx/src/retrolibx/gui/": "src/frontend_gui/",
        "retrolibx/src/retrolibx/application/": "src/library_converter/",
        "retrolibx/src/frontend_platforms": "src/frontend_platforms",
        "retrolibx/src/retrolibx": "src/retrolibx",
        "retrolibx/tests/": "tests/",
        "retrolibx/docs/": "docs/engine/",
        "../retrolibx/README.md": "../README.md",
        "retrolibx/README.md": "README.md",
        "retrolibx/pyproject.toml": "pyproject.toml",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    path.write_text(text, encoding="utf-8")
# Move Pillow from the optional desktop dependency to the cross-platform theme tool.
path = ROOT / "uv.lock"
text = path.read_text(encoding="utf-8")
start = text.index('name = "retrolibx"\n')
end = text.index('\n[[package]]', start)
block = text[start:end].replace('    { name = "lxml" },', '    { name = "lxml" },\n    { name = "pillow" },')
block = block.replace('    { name = "pillow", marker = "sys_platform == \'win32\'" },\n', '')
block = block.replace('{ name = "pillow", marker = "sys_platform == \'win32\' and extra == \'desktop\'", specifier = ">=10" }', '{ name = "pillow", specifier = ">=10" }')
path.write_text(text[:start] + block + text[end:], encoding="utf-8")
path = ROOT / "tests/gui/test_gui_state.py"
text = path.read_text(encoding="utf-8").replace('with patch("frontend_common.state.write_json", side_effect=PermissionError("read-only")):\n            with self.assertRaises(PermissionError):\n                store.save_definitions(changed)', 'with patch("frontend_common.files.write_json", side_effect=PermissionError("read-only")):\n            with self.assertRaises(PermissionError):\n                store.save_definitions(changed)')
path.write_text(text, encoding="utf-8")
