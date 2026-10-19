"""One-time path relocation after the checkout rename; no product imports/tests.

Run with the retained environment's Python after moving the checkout:
    python tools/migrations/rename_handheld_toolbox.py <old-checkout-path>
The directory move itself belongs to the calling PowerShell operation.
"""
import base64
import configparser
import csv
from datetime import datetime
import hashlib
import io
import json
from pathlib import Path
import shutil
import sys
import tomllib

from pip._vendor.distlib.scripts import ScriptMaker


root = Path(__file__).resolve().parents[2]
old_root = Path(sys.argv[1]).resolve()
if root.name != "HandheldToolbox" or old_root.parent != root.parent or old_root == root:
    raise ValueError("Only the sibling checkout rename to HandheldToolbox is supported")

venv = root / "retrolibx/.venv"
scripts = venv / "Scripts"
site = venv / "Lib/site-packages"
backup = root / "workspace/backups/migrations" / (
    "rename-handheld-toolbox-" + datetime.now().strftime("%Y%m%d-%H%M%S"))
if backup.exists():
    raise FileExistsError(backup)

# Read entry-point metadata before touching any Windows launcher. Do not patch
# executable bytes: regenerate the existing scripts with bundled pip/distlib.
entries = {}
for metadata in site.glob("*.dist-info/entry_points.txt"):
    config = configparser.ConfigParser(interpolation=None)
    config.optionxform = str
    config.read(metadata, encoding="utf-8")
    for group in ("console_scripts", "gui_scripts"):
        if config.has_section(group):
            for name, entry in config.items(group):
                entries[name + ".exe"] = (name, entry, group == "gui_scripts")

if "pip.exe" in entries:
    pip_variant = "pip" + str(sys.version_info.major) + "." + str(sys.version_info.minor)
    entries[pip_variant + ".exe"] = (pip_variant, entries["pip.exe"][1], False)

launchers = [path for path in scripts.glob("*.exe")
             if str(old_root).encode("utf-8") in path.read_bytes()]
unknown = [path.name for path in launchers if path.name not in entries]
if unknown:
    raise ValueError("No entry-point metadata for: " + ", ".join(unknown))

replacements = [
    (json.dumps(str(old_root))[1:-1], json.dumps(str(root))[1:-1]),
    (str(old_root), str(root)),
    (old_root.as_posix(), root.as_posix()),
    (old_root.as_uri(), root.as_uri()),
]
changed = set()


def preserve(path):
    relative = path.resolve().relative_to(root)
    target = backup / "files" / relative
    if path.exists() and not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)


def relocate(path):
    raw = path.read_bytes()
    # UTF-8 text only; binary launchers are handled through ScriptMaker.
    text = raw.decode("utf-8-sig")
    updated = text
    for old, new in replacements:
        updated = updated.replace(old, new)
    if updated != text:
        preserve(path)
        prefix = b"\xef\xbb\xbf" if raw.startswith(b"\xef\xbb\xbf") else b""
        path.write_bytes(prefix + updated.encode("utf-8"))
        changed.add(path.resolve())


text_paths = [root / "settings.json"]
for directory in ("workspace/config", "workspace/backups", "workspace/temp"):
    text_paths.extend((root / directory).rglob("*.json"))
text_paths.extend(site.glob("*.pth"))
text_paths.extend(site.glob("*.dist-info/direct_url.json"))
text_paths.extend(path for path in scripts.iterdir()
                  if path.name.startswith("activate") and path.is_file())
for path in text_paths:
    if path.is_file() and not path.is_relative_to(backup):
        relocate(path)

maker = ScriptMaker(None, str(scripts))
maker.clobber = True
maker.variants = {""}
for path in launchers:
    name, entry, gui = entries[path.name]
    preserve(path)
    executable = scripts / "python.exe"
    maker.executable = '"' + str(executable) + '"'
    changed.update(Path(file).resolve() for file in maker.make(name + " = " + entry, {"gui": gui}))

# Expose the current project's declared commands in this source environment.
# Existing engine/dependency metadata retains its own identity and licenses.
project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]
for group, gui in (("scripts", False), ("gui-scripts", True)):
    for name, entry in project.get(group, {}).items():
        target = scripts / (name + ".exe")
        preserve(target)
        executable = scripts / "python.exe"
        maker.executable = '"' + str(executable) + '"'
        changed.update(Path(file).resolve() for file in maker.make(name + " = " + entry, {"gui": gui}))

# Maintain installed-package RECORD hashes for the files this migration changed.
for record in site.glob("*.dist-info/RECORD"):
    rows = list(csv.reader(io.StringIO(record.read_text(encoding="utf-8"))))
    touched = False
    for row in rows:
        path = (site / row[0]).resolve()
        if path in changed:
            data = path.read_bytes()
            digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode("ascii")
            row[1:] = ["sha256=" + digest, str(len(data))]
            touched = True
    if touched:
        preserve(record)
        output = io.StringIO(newline="")
        csv.writer(output).writerows(rows)
        record.write_bytes(output.getvalue().encode("utf-8"))
        changed.add(record.resolve())

backup.mkdir(parents=True, exist_ok=True)
manifest = {"old_root": str(old_root), "new_root": str(root),
            "updated_files": sorted(str(path.relative_to(root)) for path in changed),
            "environment": "Existing Python and dependencies retained; launchers regenerated offline",
            "tests": "not run", "codex_project_settings": "user will update manually"}
(backup / "migration.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps({"updated_files": len(changed), "backup": str(backup)}, ensure_ascii=False))
