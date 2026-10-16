"""Extract every available platform image for the four approved GUI card styles.

This is a development asset import, not part of the installed application.
"""
from pathlib import Path
import hashlib
import json
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
ORIGINAL = ROOT / "test_data/themes/original"
OUTPUT = ROOT / "src/frontend_gui/assets/cards"
SOURCES = {
    "canvas": ("canvas-es-de", "_inc/carousel-icons-capsule"),
    "aura": ("aura-es-de", "_inc/default-art"),
    "alekfull-nx": ("alekfull-nx-es-de", "_inc/systems/backgrounds"),
    "iisu": ("iisu-interpreted-es-de", "_inc/systems/artwork"),
}
manifest = {}
for style, (theme, folder) in SOURCES.items():
    source = ORIGINAL / theme / folder
    assets = {}
    if style == "aura":
        paths = [(p.name, p / (p.name + "-clear-full-w-char.webp")) for p in source.iterdir() if p.is_dir()]
    else:
        paths = [(p.stem, p) for p in source.iterdir() if p.suffix.lower() in {".webp", ".png", ".jpg", ".jpeg"}]
    # Retain the real previously approved Canvas custom-platform illustrations too.
    if style == "canvas":
        existing = {name.casefold() for name, _path in paths}
        paths += [(p.stem, p) for p in (ROOT / "docs/design/assets/legacy-platforms").glob("*.webp") if p.stem.casefold() not in existing]
    destination = OUTPUT / style
    destination.mkdir(parents=True, exist_ok=True)
    for name, path in sorted(paths):
        if not path.is_file():
            continue
        filename = hashlib.sha256(name.encode("utf-8")).hexdigest()[:20] + ".webp"
        with Image.open(path) as image:
            image.thumbnail((640, 480), Image.Resampling.LANCZOS)
            image.convert("RGBA").save(destination / filename, quality=90, method=6)
        assets[name.casefold()] = {"file": filename, "platform": name, "source": str(path.relative_to(ROOT))}
    manifests = [p for p in (ORIGINAL / theme).iterdir() if p.is_file() and any(key in p.name.casefold() for key in ("license", "copying"))]
    license_text = "\n\n".join(p.read_text(encoding="utf-8", errors="replace") for p in manifests)
    if license_text:
        (destination / "SOURCE-LICENSE.txt").write_text(license_text, encoding="utf-8")
    readme = ORIGINAL / theme / "README.md"
    notice = "Source: " + str((ORIGINAL / theme).relative_to(ROOT)) + "\n\n"
    if readme.is_file():
        notice += readme.read_text(encoding="utf-8", errors="replace")
    (destination / "SOURCE-NOTICE.txt").write_text(notice, encoding="utf-8")
    manifest[style] = {"source_theme": theme, "source_folder": folder, "count": len(assets),
                       "bytes": sum(p.stat().st_size for p in destination.glob("*.webp")), "assets": assets}
OUTPUT.mkdir(parents=True, exist_ok=True)
(OUTPUT / "index.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps({key: {"count": value["count"], "bytes": value["bytes"]} for key, value in manifest.items()}))
