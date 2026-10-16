"""Export the selected, unchanged artwork to a Windows multi-resolution ICO."""
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "docs/design/assets/app-icons/handheld-vertical-01.png"
OUTPUT = ROOT / "src/frontend_gui/assets/app/app.ico"
SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)


if __name__ == "__main__":
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(SOURCE) as image:
        image.convert("RGBA").save(OUTPUT, format="ICO", sizes=[(size, size) for size in SIZES])
    print(OUTPUT)
