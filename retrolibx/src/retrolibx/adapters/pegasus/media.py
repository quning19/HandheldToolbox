"""Pegasus asset names mapped to frontend-independent media roles."""

ALIASES = {
    "box_front": ("box_front", "boxfront", "boxart2d"),
}


def canonical_role(name: str) -> str:
    return next((role for role, aliases in ALIASES.items() if name in aliases), name)


