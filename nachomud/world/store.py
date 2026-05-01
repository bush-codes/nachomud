"""Persistence for world state: rooms, mobs, items, graph.

Three first-class stores per world (DESIGN.md §8):
  data/world/<world_id>/rooms/<room_id>.json   — immutable skeleton + flags
  data/world/<world_id>/mobs.json              — all mob instances by mob_id
  data/world/<world_id>/items.json             — all item instances by item_id
  data/world/<world_id>/graph.json             — adjacency map
  data/world/<world_id>/meta.json              — world-level metadata

Plus a hand-authored `factions.json` (read-only, optional override).

All writes are atomic (write to .tmp, rename) so a crash mid-write can't leave
a partial file. All loads route through `migrations.migrate()`.
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, fields
from typing import Any

from nachomud.characters.migrations import migrate
from nachomud.models import Item, Mob, NPC, Room

# ── Schema versions ──
SCHEMA_VERSION_ROOM = 1
SCHEMA_VERSION_MOB = 1
SCHEMA_VERSION_ITEM = 1
SCHEMA_VERSION_GRAPH = 1
SCHEMA_VERSION_META = 1

# ── Paths ──
DATA_ROOT = os.environ.get("NACHOMUD_DATA_ROOT", os.path.join("data", "world"))


def world_dir(world_id: str) -> str:
    return os.path.join(DATA_ROOT, world_id)


def rooms_dir(world_id: str) -> str:
    return os.path.join(world_dir(world_id), "rooms")


def _ensure_world_dirs(world_id: str) -> None:
    os.makedirs(rooms_dir(world_id), exist_ok=True)


def _atomic_write_json(path: str, payload: Any) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(payload, f, indent=2, sort_keys=False)
    os.replace(tmp, path)


def _read_json(path: str) -> dict:
    with open(path) as f:
        return json.load(f)


# ── Item (de)serialization ──

def item_to_dict(item: Item | None) -> dict | None:
    if item is None:
        return None
    return asdict(item)


def item_from_dict(d: dict | None) -> Item | None:
    if d is None:
        return None
    field_names = {f.name for f in fields(Item)}
    return Item(**{k: v for k, v in d.items() if k in field_names})


# ── Mob (de)serialization ──

def mob_to_dict(mob: Mob) -> dict:
    d = asdict(mob)
    d["schema_version"] = SCHEMA_VERSION_MOB
    return d


def mob_from_dict(d: dict) -> Mob:
    d = migrate("mob", dict(d), SCHEMA_VERSION_MOB)
    field_names = {f.name for f in fields(Mob)}
    payload = {k: v for k, v in d.items() if k in field_names}
    # Reconstruct loot Items
    loot_dicts = payload.get("loot", [])
    payload["loot"] = [item_from_dict(x) for x in loot_dicts if x is not None]
    return Mob(**payload)


# ── NPC (de)serialization ──

def npc_to_dict(npc: NPC) -> dict:
    d = asdict(npc)
    if npc.item is not None:
        d["item"] = item_to_dict(npc.item)
    return d


def npc_from_dict(d: dict) -> NPC:
    field_names = {f.name for f in fields(NPC)}
    payload = {k: v for k, v in d.items() if k in field_names}
    if payload.get("item") is not None:
        payload["item"] = item_from_dict(payload["item"])
    return NPC(**payload)


# ── Room (de)serialization ──

def room_to_dict(room: Room) -> dict:
    return {
        "room_id": room.id,
        "name": room.name,
        "description": room.description,
        "exits": dict(room.exits),
        "zone_tag": room.zone_tag,
        "spawned_npcs": [npc_to_dict(n) for n in room.npcs],
        "state": {"flags": dict(room.flags)},
        "schema_version": SCHEMA_VERSION_ROOM,
    }


def room_from_dict(d: dict) -> Room:
    d = migrate("room", dict(d), SCHEMA_VERSION_ROOM)
    npcs = [npc_from_dict(n) for n in d.get("spawned_npcs", [])]
    flags = d.get("state", {}).get("flags", {})
    return Room(
        id=d["room_id"],
        name=d.get("name", d["room_id"]),
        description=d.get("description", ""),
        exits=dict(d.get("exits", {})),
        zone_tag=d.get("zone_tag", ""),
        npcs=npcs,
        flags=dict(flags),
    )


# ── Room store ──

def room_path(world_id: str, room_id: str) -> str:
    return os.path.join(rooms_dir(world_id), f"{room_id}.json")


def save_room(world_id: str, room: Room) -> None:
    _ensure_world_dirs(world_id)
    _atomic_write_json(room_path(world_id, room.id), room_to_dict(room))


def load_room(world_id: str, room_id: str) -> Room:
    return room_from_dict(_read_json(room_path(world_id, room_id)))


def room_exists(world_id: str, room_id: str) -> bool:
    return os.path.isfile(room_path(world_id, room_id))


def update_room_flags(world_id: str, room_id: str, flags: dict[str, bool]) -> None:
    """Merge `flags` into the room's mutable state.flags dict."""
    payload = _read_json(room_path(world_id, room_id))
    payload.setdefault("state", {}).setdefault("flags", {}).update(flags)
    _atomic_write_json(room_path(world_id, room_id), payload)


def list_rooms(world_id: str) -> list[str]:
    d = rooms_dir(world_id)
    if not os.path.isdir(d):
        return []
    return sorted(f[:-5] for f in os.listdir(d) if f.endswith(".json"))


# ── Mob registry ──

def mobs_path(world_id: str) -> str:
    return os.path.join(world_dir(world_id), "mobs.json")


def load_mobs(world_id: str) -> dict[str, Mob]:
    path = mobs_path(world_id)
    if not os.path.isfile(path):
        return {}
    raw = _read_json(path)
    return {mid: mob_from_dict(d) for mid, d in raw.items()}


def save_mobs(world_id: str, mobs: dict[str, Mob]) -> None:
    _ensure_world_dirs(world_id)
    payload = {mid: mob_to_dict(m) for mid, m in mobs.items()}
    _atomic_write_json(mobs_path(world_id), payload)


def get_mob(world_id: str, mob_id: str) -> Mob | None:
    return load_mobs(world_id).get(mob_id)


def update_mob(world_id: str, mob: Mob) -> None:
    mobs = load_mobs(world_id)
    mobs[mob.mob_id] = mob
    save_mobs(world_id, mobs)


def add_mob(world_id: str, mob: Mob) -> None:
    """Add a freshly-spawned mob to the registry."""
    update_mob(world_id, mob)


def mobs_in_room(world_id: str, room_id: str, alive_only: bool = True) -> list[Mob]:
    return [
        m for m in load_mobs(world_id).values()
        if m.current_room == room_id and (not alive_only or m.alive)
    ]


def living_mobs_in_zone(world_id: str, zone_tag: str) -> list[Mob]:
    return [m for m in load_mobs(world_id).values() if m.zone_tag == zone_tag and m.alive]


# ── Item registry ──

def items_path(world_id: str) -> str:
    return os.path.join(world_dir(world_id), "items.json")


def load_items(world_id: str) -> dict[str, dict]:
    """Items are stored as raw dicts (Item dataclass + 'item_id' + 'location')."""
    path = items_path(world_id)
    if not os.path.isfile(path):
        return {}
    return _read_json(path)


def save_items(world_id: str, items: dict[str, dict]) -> None:
    _ensure_world_dirs(world_id)
    _atomic_write_json(items_path(world_id), items)


def get_item(world_id: str, item_id: str) -> dict | None:
    return load_items(world_id).get(item_id)


def add_item(world_id: str, item_id: str, item: Item, location: str) -> None:
    """Register a new item instance at `location` (e.g. 'room:silverbrook.smithy')."""
    items = load_items(world_id)
    payload = item_to_dict(item) or {}
    payload["item_id"] = item_id
    payload["location"] = location
    payload["schema_version"] = SCHEMA_VERSION_ITEM
    items[item_id] = payload
    save_items(world_id, items)


def update_item_location(world_id: str, item_id: str, new_location: str) -> None:
    items = load_items(world_id)
    if item_id not in items:
        raise KeyError(f"Unknown item: {item_id}")
    items[item_id]["location"] = new_location
    save_items(world_id, items)


def items_in_room(world_id: str, room_id: str) -> list[dict]:
    target = f"room:{room_id}"
    return [i for i in load_items(world_id).values() if i.get("location") == target]


def items_in_inventory(world_id: str, player_id: str) -> list[dict]:
    target = f"inv:{player_id}"
    return [i for i in load_items(world_id).values() if i.get("location") == target]


# ── Graph (adjacency) ──

def graph_path(world_id: str) -> str:
    return os.path.join(world_dir(world_id), "graph.json")


def load_graph(world_id: str) -> dict[str, dict[str, str]]:
    path = graph_path(world_id)
    if not os.path.isfile(path):
        return {}
    raw = _read_json(path)
    # Strip schema_version if present at top level
    raw.pop("schema_version", None)
    return raw


def save_graph(world_id: str, graph: dict[str, dict[str, str]]) -> None:
    _ensure_world_dirs(world_id)
    payload = dict(graph)
    payload["schema_version"] = SCHEMA_VERSION_GRAPH
    _atomic_write_json(graph_path(world_id), payload)


def add_edge(world_id: str, from_room: str, direction: str, to_room: str,
             bidirectional: bool = True) -> None:
    g = load_graph(world_id)
    g.setdefault(from_room, {})[direction] = to_room
    if bidirectional:
        opp = opposite_direction(direction)
        if opp:
            g.setdefault(to_room, {})[opp] = from_room
    save_graph(world_id, g)


# Re-exported for back-compat with code that calls world_store.opposite_direction.
from nachomud.world.directions import opposite as opposite_direction  # noqa: E402


# ── Meta ──

def meta_path(world_id: str) -> str:
    return os.path.join(world_dir(world_id), "meta.json")


def save_meta(world_id: str, meta: dict) -> None:
    _ensure_world_dirs(world_id)
    payload = dict(meta)
    payload["schema_version"] = SCHEMA_VERSION_META
    _atomic_write_json(meta_path(world_id), payload)


def load_meta(world_id: str) -> dict:
    path = meta_path(world_id)
    if not os.path.isfile(path):
        return {}
    return _read_json(path)


def init_world(world_id: str, *, seed: int | None = None, theme: str = "default",
               owner_id: str | None = None) -> None:
    """Create empty world skeleton if it doesn't exist."""
    _ensure_world_dirs(world_id)
    if not os.path.isfile(meta_path(world_id)):
        save_meta(world_id, {
            "world_id": world_id,
            "seed": seed,
            "theme": theme,
            "owner_id": owner_id,
            "created_at": _now_iso(),
        })
    if not os.path.isfile(mobs_path(world_id)):
        save_mobs(world_id, {})
    if not os.path.isfile(items_path(world_id)):
        save_items(world_id, {})
    if not os.path.isfile(graph_path(world_id)):
        save_graph(world_id, {})


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()
