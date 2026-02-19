from __future__ import annotations

import json
import os
import random

import config
from models import Item, Mob, NPC, Room

WORLDS_DIR = os.path.join("data", "worlds")
LEGACY_WORLD_FILE = os.path.join("data", "world.json")


def _parse_item(data: dict) -> Item:
    return Item(
        name=data.get("name", "Unknown"),
        slot=data.get("slot", "weapon"),
        atk=data.get("atk", 0),
        pdef=data.get("pdef", 0),
        mdef=data.get("mdef", 0),
        mdmg=data.get("mdmg", 0),
        allowed_classes=data.get("allowed_classes", None),
    )


def _parse_mob(data: dict) -> Mob:
    loot = [_parse_item(i) for i in data.get("loot", [])]
    return Mob(
        name=data["name"],
        hp=data["hp"],
        max_hp=data["max_hp"],
        atk=data["atk"],
        mdef=data.get("mdef", 0),
        pdef=data.get("pdef", 0),
        is_boss=data.get("is_boss", False),
        loot=loot,
        speed=data.get("speed", 3),
        abilities=data.get("abilities", ["attack"]),
        personality=data.get("personality", ""),
    )


def _parse_npc(data: dict) -> NPC:
    item = _parse_item(data["item"]) if data.get("item") else None
    return NPC(
        name=data["name"],
        title=data.get("title", ""),
        dialogue=data.get("dialogue", []),
        item=item,
        interactions_left=random.randint(1, 2),
    )


def list_worlds() -> list[dict]:
    """Scan data/worlds/*.json and return [{id, name, description}] from each file's meta block."""
    worlds = []
    if not os.path.isdir(WORLDS_DIR):
        return worlds
    for fname in sorted(os.listdir(WORLDS_DIR)):
        if not fname.endswith(".json"):
            continue
        world_id = fname[:-5]  # strip .json
        fpath = os.path.join(WORLDS_DIR, fname)
        try:
            with open(fpath) as f:
                data = json.load(f)
            meta = data.get("meta", {})
            worlds.append({
                "id": world_id,
                "name": meta.get("name", world_id),
                "description": meta.get("description", ""),
            })
        except (json.JSONDecodeError, OSError):
            continue
    return worlds


def build_world(world_id: str = "shadowfell") -> dict[str, Room]:
    world_file = os.path.join(WORLDS_DIR, f"{world_id}.json")
    if os.path.exists(world_file):
        print(f"Loading world from {world_file}...", flush=True)
        with open(world_file) as f:
            world_data = json.load(f)
    elif os.path.exists(LEGACY_WORLD_FILE):
        # Backwards compat: fall back to data/world.json
        print(f"Loading world from {LEGACY_WORLD_FILE}...", flush=True)
        with open(LEGACY_WORLD_FILE) as f:
            world_data = json.load(f)
    else:
        from narrator import generate_world_json
        print("Generating world with LLM narrator...", flush=True)
        world_data = generate_world_json()
        os.makedirs(WORLDS_DIR, exist_ok=True)
        with open(world_file, "w") as f:
            json.dump(world_data, f, indent=2)
        print(f"World saved to {world_file}", flush=True)

    # Set quest description from world meta
    meta = world_data.get("meta", {})
    if meta.get("description"):
        config.QUEST_DESCRIPTION = meta["description"]

    rooms: dict[str, Room] = {}
    for room_data in world_data["rooms"]:
        mobs = [_parse_mob(m) for m in room_data.get("mobs", [])]
        npcs = [_parse_npc(n) for n in room_data.get("npcs", [])]
        items = [_parse_item(i) for i in room_data.get("items", [])]

        description = room_data.get("description", "")

        room = Room(
            id=room_data["id"],
            name=room_data["name"],
            description=description,
            exits=room_data.get("exits", {}),
            mobs=mobs,
            npcs=npcs,
            items=items,
            visited=bool(description),
        )
        # Set mob room_ids so initiative system can find them
        for mob in mobs:
            mob.room_id = room.id
        rooms[room.id] = room

    # Validate bidirectional exits
    opposite = {"n": "s", "s": "n", "e": "w", "w": "e"}
    for room in rooms.values():
        for direction, target_id in list(room.exits.items()):
            if target_id not in rooms:
                del room.exits[direction]
                continue
            target = rooms[target_id]
            opp = opposite.get(direction)
            if opp and opp not in target.exits:
                target.exits[opp] = room.id

    print(f"World loaded: {len(rooms)} rooms.", flush=True)
    return rooms


def describe_room(room: Room) -> str:
    if not room.visited:
        from narrator import generate_room_description
        context_parts = []
        if room.mobs:
            mob_names = ", ".join(m.name for m in room.mobs if m.hp > 0)
            if mob_names:
                context_parts.append(f"Contains: {mob_names}")
        if room.npcs:
            npc_names = ", ".join(f"{n.name} the {n.title}" for n in room.npcs)
            context_parts.append(f"NPCs: {npc_names}")
        context = ". ".join(context_parts) if context_parts else "Empty corridor"

        room.description = generate_room_description(room.name, context)
        room.visited = True

    return room.description


def get_room_state(room: Room, agent_names_here: list[str]) -> str:
    parts = [f"Room: {room.name}"]
    if room.description:
        parts.append(room.description)

    exits = ", ".join(f"{d} -> {rooms_id}" for d, rooms_id in room.exits.items())
    parts.append(f"Exits: {exits}")

    living_mobs = [m for m in room.mobs if m.hp > 0]
    if living_mobs:
        mob_strs = [f"{m.name} (HP:{m.hp}/{m.max_hp}, ATK:{m.atk})" for m in living_mobs]
        parts.append(f"Enemies: {', '.join(mob_strs)}")
    else:
        parts.append("Enemies: none")

    if room.npcs:
        npc_strs = [f"{n.name} the {n.title}" for n in room.npcs]
        parts.append(f"NPCs: {', '.join(npc_strs)}")

    if room.items:
        item_strs = [i.name for i in room.items]
        parts.append(f"Items on ground: {', '.join(item_strs)}")
    else:
        parts.append("Items on ground: none")

    if agent_names_here:
        parts.append(f"Allies here: {', '.join(agent_names_here)}")

    return "\n".join(parts)


def _item_stat_str(item: "Item", agent_class: str = "") -> str:
    """Short stat string for an item: 'Rusty Sword (weapon, ATK:3)'.

    If agent_class is provided and the item has allowed_classes that don't
    include the agent's class, appends [CANNOT USE].
    """
    stats = []
    if item.atk:
        stats.append(f"ATK:{item.atk}")
    if item.pdef:
        stats.append(f"PDEF:{item.pdef}")
    if item.mdef:
        stats.append(f"MDEF:{item.mdef}")
    if item.mdmg:
        stats.append(f"MDMG:{item.mdmg}")
    base = f"{item.name} ({item.slot}, {', '.join(stats)})" if stats else f"{item.name} ({item.slot})"
    if agent_class and item.allowed_classes and agent_class not in item.allowed_classes:
        base += " [CANNOT USE]"
    return base


def build_sensory_context(
    room: Room,
    agent_names_here: list[str],
    rooms: dict[str, "Room"],
    agent_name: str,
    visited_rooms: list[str] | None = None,
    agent_class: str = "",
) -> str:
    """Build full sensory awareness: current room, adjacent rooms, allies."""
    parts = [f"You are in: {room.name}"]
    if room.description:
        parts.append(room.description)

    # Enemies in current room
    living_mobs = [m for m in room.mobs if m.hp > 0]
    if living_mobs:
        mob_strs = [f"{m.name} (HP:{m.hp}/{m.max_hp}, ATK:{m.atk})" for m in living_mobs]
        parts.append(f"Enemies here: {', '.join(mob_strs)}")
    else:
        parts.append("Enemies here: none")

    # Items with stats so agent can compare against equipment
    if room.items:
        item_strs = [_item_stat_str(i, agent_class) for i in room.items]
        parts.append(f"Items on ground: {', '.join(item_strs)}")
    else:
        parts.append("Items on ground: none")

    # NPCs
    if room.npcs:
        npc_strs = [f"{n.name} the {n.title}" for n in room.npcs]
        parts.append(f"NPCs here: {', '.join(npc_strs)}")

    # Allies
    allies = [n for n in agent_names_here if n != agent_name]
    if allies:
        parts.append(f"Allies here: {', '.join(allies)}")
    else:
        parts.append("Allies here: none (you are alone)")

    # Adjacent rooms (names only — no details to avoid confusing targets)
    dir_names = {"n": "north", "s": "south", "e": "east", "w": "west"}
    parts.append("")
    parts.append("Exits:")
    for d in ("n", "s", "e", "w"):
        if d in room.exits:
            adj = rooms[room.exits[d]]
            describe_room(adj)
            parts.append(f"  {dir_names[d]} ({d}): {adj.name}")

    # Rooms visited so far (helps agent avoid backtracking)
    if visited_rooms:
        parts.append(f"\nRooms visited: {', '.join(visited_rooms)}")

    return "\n".join(parts)
