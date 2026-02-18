from __future__ import annotations

import json
import os

from models import Item, Mob, NPC, Room

WORLD_FILE = os.path.join("data", "world.json")


def _parse_item(data: dict) -> Item:
    return Item(
        name=data.get("name", "Unknown"),
        slot=data.get("slot", "weapon"),
        atk=data.get("atk", 0),
        pdef=data.get("pdef", 0),
        mdef=data.get("mdef", 0),
        mdmg=data.get("mdmg", 0),
    )


def _parse_mob(data: dict) -> Mob:
    loot = [_parse_item(i) for i in data.get("loot", [])]
    return Mob(
        name=data["name"],
        hp=data["hp"],
        max_hp=data["max_hp"],
        atk=data["atk"],
        mdef=data.get("mdef", 0),
        is_boss=data.get("is_boss", False),
        loot=loot,
    )


def _parse_npc(data: dict) -> NPC:
    item = _parse_item(data["item"]) if data.get("item") else None
    return NPC(
        name=data["name"],
        title=data.get("title", ""),
        dialogue=data.get("dialogue", []),
        item=item,
    )


def build_world() -> dict[str, Room]:
    if os.path.exists(WORLD_FILE):
        print(f"Loading world from {WORLD_FILE}...", flush=True)
        with open(WORLD_FILE) as f:
            world_data = json.load(f)
    else:
        from narrator import generate_world_json
        print("Generating world with LLM narrator...", flush=True)
        world_data = generate_world_json()
        os.makedirs(os.path.dirname(WORLD_FILE), exist_ok=True)
        with open(WORLD_FILE, "w") as f:
            json.dump(world_data, f, indent=2)
        print(f"World saved to {WORLD_FILE}", flush=True)

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


def build_sensory_context(
    room: Room,
    agent_names_here: list[str],
    rooms: dict[str, "Room"],
    agent_name: str,
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

    # Items
    if room.items:
        item_strs = [i.name for i in room.items]
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

    # Adjacent rooms
    dir_names = {"n": "north", "s": "south", "e": "east", "w": "west"}
    parts.append("")
    parts.append("Nearby:")
    for d in ("n", "s", "e", "w"):
        if d in room.exits:
            adj = rooms[room.exits[d]]
            describe_room(adj)
            adj_mobs = [m for m in adj.mobs if m.hp > 0]
            adj_info = adj.name
            details = []
            if adj_mobs:
                details.append(f"Enemies: {', '.join(m.name for m in adj_mobs)}")
            if adj.npcs:
                details.append(f"NPCs: {', '.join(n.name for n in adj.npcs)}")
            if adj.items:
                details.append(f"Items: {', '.join(i.name for i in adj.items)}")
            if details:
                adj_info += f" ({', '.join(details)})"
            parts.append(f"  {dir_names[d]} ({d}): {adj_info}")
        else:
            parts.append(f"  {dir_names[d]}: no exit")

    return "\n".join(parts)
