"""Loader for the hand-authored starter town.

Reads `nachomud/world/towns/<name>.json` and writes it into a world's
stores (rooms, graph, npcs as part of rooms). Idempotent: skips rooms
that already exist (so player progress isn't blown away on reboot).
"""
from __future__ import annotations

import json
import os

import nachomud.world.store as world_store
from nachomud.models import NPC, Room

STARTER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "towns"))

INN_FLAG = "is_inn"


def load_starter_doc(name: str = "silverbrook") -> dict:
    path = os.path.join(STARTER_DIR, f"{name}.json")
    with open(path) as f:
        return json.load(f)


def seed_world(world_id: str = "default", town: str = "silverbrook",
               refresh: bool = True) -> int:
    """Seed the world's rooms + graph from the named starter town.

    Starter-town rooms are *hand-authored canonical content* — they belong to
    the developer, not to the procedural world. By default this refreshes them
    on every boot, picking up any JSON edits (new NPCs, new wares, fixed
    descriptions) while preserving the room's mutable flags (e.g. door_unlocked).

    Pass refresh=False to behave like the old idempotent seed (skip existing
    rooms entirely).

    Returns the number of rooms written (created or refreshed).
    """
    doc = load_starter_doc(town)
    world_store.init_world(world_id, theme=doc["meta"].get("name", town))

    # Build NPC index by location for assignment to rooms
    npcs_by_starting_location: dict[str, list[NPC]] = {}
    for n in doc.get("npcs", []):
        # NPC's "starting" location is the one where their routine has them at the
        # earliest morning hour. Failing that, the first routine entry.
        routines = n.get("routines", [])
        location = ""
        if routines:
            # find a daytime location (8am)
            for r in routines:
                if r["start_hr"] <= 8 < r["end_hr"]:
                    location = r["location_id"]
                    break
            if not location:
                location = routines[0]["location_id"]

        npc = NPC(
            npc_id=n["npc_id"],
            name=n["name"],
            title=n["title"],
            personality=n.get("personality", ""),
            faction=n.get("faction", "none"),
            routines=list(routines),
            wares=list(n.get("wares", [])),
            lore=list(n.get("lore", [])),
        )
        if location and not location.startswith("else"):
            npcs_by_starting_location.setdefault(location, []).append(npc)

    # Persist rooms
    written = 0
    for r in doc["rooms"]:
        rid = r["room_id"]
        existing_flags: dict[str, bool] = {}
        if world_store.room_exists(world_id, rid):
            if not refresh:
                continue
            try:
                existing_flags = dict(world_store.load_room(world_id, rid).flags)
            except Exception:
                existing_flags = {}

        flags: dict[str, bool] = dict(existing_flags)
        if r.get(INN_FLAG):
            flags[INN_FLAG] = True

        room = Room(
            id=rid,
            name=r["name"],
            description=r["description"],
            exits=dict(r.get("exits", {})),
            zone_tag=r.get("zone_tag", ""),
            npcs=npcs_by_starting_location.get(rid, []),
            flags=flags,
        )
        world_store.save_room(world_id, room)
        written += 1

    # Persist graph (always, idempotently)
    g = world_store.load_graph(world_id)
    for r in doc["rooms"]:
        rid = r["room_id"]
        for direction, dest in r.get("exits", {}).items():
            g.setdefault(rid, {})[direction] = dest
    world_store.save_graph(world_id, g)

    return written


def starter_spawn_room(town: str = "silverbrook") -> str:
    """Default spawn room id for a starter town (inn if any, else first room)."""
    doc = load_starter_doc(town)
    for r in doc["rooms"]:
        if r.get(INN_FLAG):
            return r["room_id"]
    return doc["rooms"][0]["room_id"] if doc["rooms"] else ""
