"""Cardinal direction constants and helpers.

Used by the world graph (edges), mob movement (BFS), the DM (validating
generated room exits), and the engine (parsing player input). One source
of truth for what counts as a direction and what its opposite is.
"""
from __future__ import annotations


# Long-form directions accepted as movement input + emitted by the DM.
VALID_DIRS: frozenset[str] = frozenset({"north", "south", "east", "west", "up", "down"})

# Short ↔ long aliases. Both forms are valid wherever a direction is taken.
SHORT_TO_LONG: dict[str, str] = {
    "n": "north", "s": "south", "e": "east", "w": "west",
    "u": "up",    "d": "down",
}
LONG_TO_SHORT: dict[str, str] = {v: k for k, v in SHORT_TO_LONG.items()}

# Opposite mapping. Defined for both long and short forms; same form goes out
# as came in (e.g. "n" → "s", "north" → "south") so callers can persist the
# canonical form they're already using.
OPPOSITES: dict[str, str] = {
    "north": "south", "south": "north",
    "east":  "west",  "west":  "east",
    "up":    "down",  "down":  "up",
    "n": "s", "s": "n",
    "e": "w", "w": "e",
    "u": "d", "d": "u",
}


def opposite(direction: str) -> str:
    """Return the opposite of `direction`, or "" if not a direction."""
    return OPPOSITES.get(direction.lower(), "")


def is_direction(s: str) -> bool:
    """True iff `s` (case-insensitive) is a recognized direction in either form."""
    return s.lower() in OPPOSITES
