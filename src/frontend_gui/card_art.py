"""Resolve within a selected style; never silently borrow a different style."""
from functools import lru_cache
import json
from pathlib import Path

ROOT = Path(__file__).with_name("assets") / "cards"


@lru_cache(maxsize=1)
def index():
    path = ROOT / "index.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def resolve_art(style, platform, mother=""):
    assets = index().get(style, {}).get("assets", {})
    for candidate in (platform, mother):
        asset = assets.get(candidate.casefold())
        if asset:
            return ROOT / style / asset["file"]
    return None
