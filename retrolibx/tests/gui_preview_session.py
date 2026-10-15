"""Open the production UI using isolated settings for approved manual testing.

Run with the project Python and a new session directory as the sole argument.
Real actions remain available; isolated settings do not sandbox device writes.
"""

from pathlib import Path
import sys
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from retrolibx.gui.app import run


if __name__ == "__main__":
    session = Path(sys.argv[1]).resolve()
    session.mkdir(parents=True, exist_ok=True)
    sys.argv = [sys.argv[0]]
    with patch("retrolibx.gui.state.app_directory", return_value=session):
        run()
