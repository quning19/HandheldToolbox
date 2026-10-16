"""Run the approved 72 checks, failed methods once, and the separately approved Iconic check.

This command does not itself grant permission. Reports prevent accidental reruns.
"""
import argparse
import json
import os
from pathlib import Path
import sys
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
os.environ["PYTHONUTF8"] = "1"
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
MODULES = [
    "tests.themes.test_generic_parser", "tests.themes.test_real_theme_graphs",
    "tests.themes.test_theme_state", "tests.platforms.test_user_catalog",
    "tests.maintenance.test_cleanup", "tests.engine.test_independent_entries",
    "tests.gui.test_gui_state", "tests.conversion.test_desktop_business",
    "tests.devices.test_desktop_discovery",
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=("initial", "failed", "iconic"))
    args = parser.parse_args()
    directory = ROOT / "jobs/independent-tools-check-20261016"
    directory.mkdir(parents=True, exist_ok=True)
    report = directory / (args.phase + ".json")
    if report.exists():
        parser.error("This approved test phase has already run; do not repeat without approval.")
    names = MODULES
    if args.phase == "failed":
        previous = json.loads((directory / "initial.json").read_text(encoding="utf-8"))
        names = previous["failed_methods"]
        if not names:
            parser.error("No failed checks to rerun.")
    elif args.phase == "iconic":
        names = ["tests.themes.test_real_theme_graphs.RealThemeGraphTests.test_iconic"]
        previous = json.loads((directory / "failed.json").read_text(encoding="utf-8"))
        if previous["failed_methods"] != names:
            parser.error("The separately approved Iconic check does not match remaining failures.")
    suite = unittest.defaultTestLoader.loadTestsFromNames(names)
    count = suite.countTestCases()
    if args.phase == "initial" and count != 72:
        parser.error(f"Expected the approved 72 checks; collected {count}. Nothing executed.")
    if args.phase == "iconic" and count != 1:
        parser.error("Expected only the separately approved Iconic check. Nothing executed.")
    started = time.monotonic()
    with (directory / (args.phase + ".log")).open("w", encoding="utf-8") as log:
        result = unittest.TextTestRunner(stream=log, verbosity=2).run(suite)
    failed = sorted({getattr(case, "test_case", case).id() for case, _trace in result.failures + result.errors})
    data = {"phase": args.phase, "tests_run": result.testsRun, "failed_methods": failed,
            "failed_subcases": len(result.failures), "errors": len(result.errors),
            "skipped": [(case.id(), reason) for case, reason in result.skipped],
            "seconds": round(time.monotonic() - started, 3), "success": result.wasSuccessful(),
            "modules": names}
    report.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(data, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result.wasSuccessful() else 1)


if __name__ == "__main__":
    main()
