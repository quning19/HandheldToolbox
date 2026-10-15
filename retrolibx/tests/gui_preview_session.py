"""Open the real preview UI using isolated settings for approved manual testing.

Run with the project Python and a new session directory as the sole argument.
No device access or conversion backend is enabled by this helper.
"""

from pathlib import Path
import sys
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from retrolibx.gui.app import run
from retrolibx.gui.library_page import ExamplePlatformLoader
from PySide6.QtCore import QThread


if __name__ == "__main__":
    session = Path(sys.argv[1]).resolve()
    session.mkdir(parents=True, exist_ok=True)
    sys.argv = [sys.argv[0]]
    # Give interactive automation enough time to cancel/switch during loading.
    # The production loader and its cancellation implementation are unchanged.
    with (
        patch("retrolibx.gui.state.app_directory", return_value=session),
        patch.object(ExamplePlatformLoader, "msleep", side_effect=lambda milliseconds: QThread.msleep(milliseconds * 5)),
    ):
        run()
