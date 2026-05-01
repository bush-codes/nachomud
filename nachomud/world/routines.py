"""NPC routine projection.

Each NPC carries a list of `(start_hr, end_hr, location_id, activity_blurb)`
tuples (stored as dicts on the NPC). Given the current game-clock hour, this
module projects which NPCs are present in a given room and what they're doing.
"""
from __future__ import annotations

from nachomud.models import NPC


def hour_in_window(hour: int, start: int, end: int) -> bool:
    """end can wrap past 24 (e.g. 22..30 means 22:00 - 06:00 next day)."""
    if end > 24:
        return hour >= start or hour < (end - 24)
    return start <= hour < end


def npc_location_at(npc: NPC, hour: int) -> tuple[str, str]:
    """Return (location_id, activity) for the NPC at the given hour.

    If no routine matches, returns ('', 'idle'). 'elsewhere' counts as a real
    location (means: NPC is not in any visible room).
    """
    for r in npc.routines:
        if hour_in_window(hour, r["start_hr"], r["end_hr"]):
            return (r["location_id"], r.get("activity", ""))
    return ("", "idle")


def npcs_in_room(npcs: list[NPC], room_id: str, hour: int) -> list[tuple[NPC, str]]:
    """Return [(npc, activity)] for NPCs whose routine puts them in `room_id` now.

    The NPC list passed in is the union of all NPCs whose home room is anywhere
    in the world (or the room's default spawn list). The routine projection
    decides whether each is actually here.
    """
    out = []
    for n in npcs:
        loc, act = npc_location_at(n, hour)
        if loc == room_id:
            out.append((n, act))
    return out


def hour_from_minute(minute: int) -> int:
    """Convert a game-clock minute (0..1440) to an hour 0..23."""
    return (minute // 60) % 24
