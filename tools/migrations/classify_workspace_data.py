"""Preserve known old GUI jobs as recovery batches; retain all unclassified data."""
import json
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parents[2]
WORKSPACE = ROOT / "workspace"
TEMP = WORKSPACE / "temp"
mapping = {}
for source in sorted(TEMP.iterdir()) if TEMP.is_dir() else []:
    if source.is_dir() and source.name.startswith(("scan-", "convert-")):
        destination = WORKSPACE / "backups/library" / source.name
        if not source.resolve().is_relative_to(TEMP.resolve()) or not destination.resolve().is_relative_to(WORKSPACE.resolve()):
            raise ValueError("Workspace move escaped expected directory")
        if destination.exists():
            raise FileExistsError(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        mapping[str(source.resolve())] = str(destination.resolve())
        source.rename(destination)
        (destination / ".frontendtrans-recovery").write_text("1\n", encoding="utf-8")
# Rewrite absolute local references only in the moved, known jobs, preserving a before-copy.
def rewrite(value):
    if isinstance(value, dict):
        return {key: rewrite(item) for key, item in value.items()}
    if isinstance(value, list):
        return [rewrite(item) for item in value]
    if isinstance(value, str):
        for old, new in mapping.items():
            if value == old or value.startswith(old + "\\"):
                return new + value[len(old):]
            before, after = old.replace("\\", "/"), new.replace("\\", "/")
            if value == before or value.startswith(before + "/"):
                return after + value[len(before):]
    return value
for destination in mapping.values():
    for path in Path(destination).rglob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, UnicodeError):
            continue
        updated = rewrite(data)
        if updated != data:
            previous = path.with_name(path.name + ".before-relocation")
            previous.write_bytes(path.read_bytes())
            path.write_text(json.dumps(updated, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
record = WORKSPACE / "backups/migrations/workspace-20261016.json"
record.parent.mkdir(parents=True, exist_ok=True)
record.write_text(json.dumps({"date": datetime.now().isoformat(), "moved": mapping, "unknown": "retained; not cleanup eligible"}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
