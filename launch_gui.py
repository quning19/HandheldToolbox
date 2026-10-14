"""Source-checkout launcher; installed/frozen applications use gui.app.run."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "retrolibx" / "src"))

from retrolibx.gui.app import run

if __name__ == "__main__":
    run()
