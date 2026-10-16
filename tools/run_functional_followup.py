"""Bounded local follow-up requested by the user; preserves outputs for review."""
from datetime import datetime
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
FILES = [
    "tests/themes/test_legacy_batches.py", "tests/engine/test_platforms.py",
    "tests/conversion/test_source_profiles.py", "tests/conversion/test_shared_esde_media.py",
    "tests/themes/test_full_exports.py", "tests/conversion/test_real_gba_workflow.py",
    "tests/gui/test_offscreen_workflows.py",
]


if __name__ == "__main__":
    stamp = datetime.now().strftime("%H%M%S-") + uuid.uuid4().hex[:4]
    reports = ROOT / "jobs" / ("functional-followup-20261016-" + stamp)
    reports.mkdir(parents=True, exist_ok=False)
    session = ROOT / "test_data" / ("fn16-" + stamp)
    session.mkdir()
    environment = dict(os.environ, PYTHONUTF8="1", PYTHONDONTWRITEBYTECODE="1",
                       QT_QPA_PLATFORM="offscreen", PYTEST_DISABLE_PLUGIN_AUTOLOAD="1",
                       FTT_FUNCTIONAL_SESSION=str(session), PYTHONPATH=str(ROOT / "src") + os.pathsep + str(ROOT))
    metadata = {"files": FILES, "session": str(session), "started": datetime.now().isoformat(),
                "scope": "Local full-theme exports, real GBA isolated copy, offscreen GUI, targeted migrated regressions. No ADB, native desktop UI, packaging or real workspace cleanup."}
    (reports / "run.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    print("REPORTS=" + str(reports), flush=True)
    with (reports / "pytest.log").open("w", encoding="utf-8") as log:
        completed = subprocess.run([sys.executable, "-B", "-m", "pytest", *FILES, "-v", "-s",
                                    "--basetemp=" + str(session / "pytest"), "--junitxml=" + str(reports / "junit.xml")],
                                   cwd=ROOT, env=environment, stdout=log, stderr=subprocess.STDOUT)
    metadata.update(exit_code=completed.returncode, finished=datetime.now().isoformat())
    (reports / "run.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    print("EXIT=" + str(completed.returncode), flush=True)
    raise SystemExit(completed.returncode)
