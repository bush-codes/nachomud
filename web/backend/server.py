"""FastAPI backend for NachoMUD web visualization."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys

# Add project root to path so we can import game modules
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, PROJECT_ROOT)
# Game engine reads world.json relative to cwd
os.chdir(PROJECT_ROOT)

from typing import Generator

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse

from agent import get_agent_action, parse_action
from combat import resolve_attack, resolve_fireball, resolve_heal, resolve_missile, resolve_poison, tick_poison
from config import AGENT_TEMPLATES, ANTHROPIC_API_KEY, LLM_BACKEND, MAX_TICKS
from memory import append_memory, build_narrative_memory, clear_memories
from models import AgentState, GameEvent, Item, Room
from world import build_world, describe_room, get_room_state

log = logging.getLogger("nachomud")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

DIRECTION_NAMES = {"n": "north", "s": "south", "e": "east", "w": "west"}

app = FastAPI(title="NachoMUD Visualization")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Serialization helpers ──────────────────────────────────────────────

def item_to_dict(item: Item) -> dict:
    return {"name": item.name, "slot": item.slot, "atk": item.atk, "pdef": item.pdef, "mdef": item.mdef, "mdmg": item.mdmg}


def mob_to_dict(mob, include_max=True) -> dict:
    d = {"name": mob.name, "hp": mob.hp, "max_hp": mob.max_hp, "atk": mob.atk, "mdef": mob.mdef, "is_boss": mob.is_boss}
    if include_max:
        d["loot"] = [item_to_dict(i) for i in mob.loot]
    return d


def agent_state_snapshot(agent: AgentState) -> dict:
    return {
        "name": agent.name,
        "hp": agent.hp,
        "max_hp": agent.max_hp,
        "mp": agent.mp,
        "max_mp": agent.max_mp,
        "room_id": agent.room_id,
        "alive": agent.alive,
        "weapon": item_to_dict(agent.weapon),
        "armor": item_to_dict(agent.armor),
        "ring": item_to_dict(agent.ring),
        "last_action": agent.last_action,
        "last_result": agent.last_result,
    }


def room_state_snapshot(room: Room) -> dict:
    return {
        "mobs": [mob_to_dict(m, include_max=False) for m in room.mobs],
        "items": [item_to_dict(i) for i in room.items],
    }


def event_to_dict(event: GameEvent) -> dict:
    return {
        "agent": event.agent,
        "action": event.action,
        "result": event.result,
        "room_id": event.room_id,
    }


# ── Game engine helpers (duplicated from main.py to avoid import issues) ──

def create_agents() -> list[AgentState]:
    agents = []
    for t in AGENT_TEMPLATES:
        agent = AgentState(
            name=t["name"],
            personality=t["personality"],
            agent_class=t["agent_class"],
            hp=t["hp"],
            max_hp=t["max_hp"],
            mp=t["mp"],
            max_mp=t["max_mp"],
            weapon=Item(**t["weapon"]),
            armor=Item(**t["armor"]),
            ring=Item(**t["ring"]),
            room_id="room_1",
        )
        clear_memories(agent.name)
        agents.append(agent)
    return agents


def agents_in_room(agents: list[AgentState], room_id: str, exclude: str = "") -> list[str]:
    return [a.name for a in agents if a.alive and a.room_id == room_id and a.name != exclude]


def equip_item(agent: AgentState, item: Item) -> None:
    if item.slot == "weapon" and item.atk > agent.weapon.atk:
        agent.weapon = item
    elif item.slot == "armor" and item.pdef > agent.armor.pdef:
        agent.armor = item
    elif item.slot == "ring" and item.mdmg > agent.ring.mdmg:
        agent.ring = item


def resolve_action(
    agent: AgentState, cmd: str, arg: str,
    rooms: dict[str, Room], agents: list[AgentState], tick: int,
) -> list[GameEvent]:
    events = []
    room = rooms[agent.room_id]

    if cmd in ("n", "s", "e", "w"):
        if cmd in room.exits:
            new_room_id = room.exits[cmd]
            agent.room_id = new_room_id
            new_room = rooms[new_room_id]
            describe_room(new_room)
            direction = DIRECTION_NAMES.get(cmd, cmd)
            result = f"{agent.name} moves {direction} to {new_room.name}."
            others = agents_in_room(agents, new_room_id, agent.name)
            mobs_here = [m for m in new_room.mobs if m.hp > 0]
            if others:
                result += f" Sees: {', '.join(others)}."
            if mobs_here:
                result += f" Enemies: {', '.join(m.name for m in mobs_here)}."
            events.append(GameEvent(tick, agent.name, f"move {cmd}", result, new_room_id))
        else:
            events.append(GameEvent(tick, agent.name, f"move {cmd}",
                                    f"No exit to the {DIRECTION_NAMES.get(cmd, cmd)}.", agent.room_id))

    elif cmd == "look":
        desc = describe_room(room)
        others = agents_in_room(agents, agent.room_id, agent.name)
        state = get_room_state(room, others)
        events.append(GameEvent(tick, agent.name, "look", state, agent.room_id))

    elif cmd == "attack":
        events.extend(resolve_attack(agent, room, arg, tick))

    elif cmd == "missile":
        events.extend(resolve_missile(agent, room, arg, tick))

    elif cmd == "fireball":
        events.extend(resolve_fireball(agent, room, tick))

    elif cmd == "poison":
        events.extend(resolve_poison(agent, room, arg, tick))

    elif cmd == "heal":
        events.extend(resolve_heal(agent, tick))

    elif cmd in ("tell", "talk"):
        parts = arg.split(None, 1)
        target_name = parts[0].lower() if parts else ""
        message = parts[1] if len(parts) > 1 else ""

        npc = None
        for n in room.npcs:
            if target_name in n.name.lower():
                npc = n
                break
        if npc:
            # Skip LLM narration for speed — use static dialogue
            dialogue = npc.dialogue[0] if npc.dialogue else "..."
            result = f"{npc.name} says: \"{dialogue}\""
            if npc.item and not npc.item_given:
                agent.inventory.append(npc.item)
                equip_item(agent, npc.item)
                result += f"\n  {npc.name} gives {agent.name} a {npc.item.name}!"
                npc.item_given = True
            events.append(GameEvent(tick, agent.name, f"tell {npc.name}", result, agent.room_id))
        else:
            target_agent = None
            for a in agents:
                if a.alive and a.room_id == agent.room_id and a.name != agent.name and target_name in a.name.lower():
                    target_agent = a
                    break
            if target_agent:
                result = f'{agent.name} tells {target_agent.name}: "{message}"'
                events.append(GameEvent(tick, agent.name, f"tell {target_agent.name}", result, agent.room_id))
            else:
                events.append(GameEvent(tick, agent.name, f"tell {target_name}",
                                        f"No one named '{target_name}' here.", agent.room_id))

    elif cmd == "say":
        others = agents_in_room(agents, agent.room_id, agent.name)
        if others:
            result = f'{agent.name} says: "{arg}" (heard by {", ".join(others)})'
        else:
            result = f'{agent.name} says: "{arg}" (nobody else is here)'
        events.append(GameEvent(tick, agent.name, "say", result, agent.room_id))

    elif cmd in ("get", "take", "pick"):
        if cmd == "pick" and arg.lower().startswith("up "):
            arg = arg[3:]
        item = None
        arg_lower = arg.lower()
        for i in room.items:
            if arg_lower in i.name.lower():
                item = i
                break
        if item:
            room.items.remove(item)
            agent.inventory.append(item)
            equip_item(agent, item)
            result = f"{agent.name} picks up {item.name}."
            if item.slot == "weapon" and agent.weapon == item:
                result += f" Equipped as weapon (ATK:{item.atk})."
            elif item.slot == "armor" and agent.armor == item:
                result += f" Equipped as armor (PDEF:{item.pdef})."
            elif item.slot == "ring" and agent.ring == item:
                result += f" Equipped as ring (MDMG:{item.mdmg})."
            events.append(GameEvent(tick, agent.name, f"get {item.name}", result, agent.room_id))
        else:
            events.append(GameEvent(tick, agent.name, f"get {arg}",
                                    f"No item named '{arg}' here.", agent.room_id))
    else:
        events.append(GameEvent(tick, agent.name, cmd,
                                f"Unknown command: {cmd}", agent.room_id))

    return events


def check_boss_defeated(rooms: dict[str, Room]) -> bool:
    for room in rooms.values():
        for mob in room.mobs:
            if mob.is_boss and mob.hp <= 0:
                return True
    return False


def all_agents_dead(agents: list[AgentState]) -> bool:
    return all(not a.alive for a in agents)


# ── Simulation runner (streaming) ──────────────────────────────────────

def simulation_stream() -> Generator[str, None, None]:
    """Sync generator that yields newline-delimited JSON: init, tick*, done."""
    rooms = build_world()
    describe_room(rooms["room_1"])
    agents = create_agents()
    log.info("Simulation started: %d agents, %d max ticks", len(agents), MAX_TICKS)

    # Build static world + agents info
    world_info = {"rooms": []}
    for room_id in sorted(rooms.keys()):
        room = rooms[room_id]
        world_info["rooms"].append({
            "id": room.id,
            "name": room.name,
            "description": room.description,
            "exits": room.exits,
            "mobs": [mob_to_dict(m) for m in room.mobs],
            "npcs": [{"name": n.name, "title": n.title} for n in room.npcs],
            "items": [item_to_dict(i) for i in room.items],
        })

    agents_info = [
        {"name": a.name, "agent_class": a.agent_class, "personality": a.personality,
         "max_hp": a.max_hp, "max_mp": a.max_mp,
         "weapon": item_to_dict(a.weapon), "armor": item_to_dict(a.armor), "ring": item_to_dict(a.ring)}
        for a in agents
    ]

    yield json.dumps({"type": "init", "world": world_info, "agents": agents_info}) + "\n"

    outcome = "timeout"
    total_ticks = 0

    for tick in range(1, MAX_TICKS + 1):
        tick_events = []

        for agent in agents:
            if not agent.alive:
                continue

            room = rooms[agent.room_id]
            others = agents_in_room(agents, agent.room_id, agent.name)
            room_state = get_room_state(room, others)

            try:
                action_str = get_agent_action(agent, room_state)
            except Exception as e:
                log.error("Tick %d: %s agent API call failed: %s", tick, agent.name, e)
                action_str = "look"

            cmd, arg = parse_action(action_str)
            log.info("Tick %d: %s -> %s", tick, agent.name, action_str)
            events = resolve_action(agent, cmd, arg, rooms, agents, tick)
            tick_events.extend(events)

            agent.last_action = action_str
            agent.last_result = events[0].result.split("\n")[0] if events else ""

        # Poison ticks
        for room in rooms.values():
            poison_events = tick_poison(room, tick)
            tick_events.extend(poison_events)

        # Update memories
        for agent in agents:
            if not agent.alive:
                continue
            agent_events = [e for e in tick_events if e.room_id == agent.room_id or e.agent == agent.name]
            if agent_events:
                room = rooms[agent.room_id]
                summary = build_narrative_memory(agent.name, agent_events, room.name)
                if summary:
                    append_memory(agent.name, tick, summary)

        # Snapshot state
        agent_states = [agent_state_snapshot(a) for a in agents]
        room_states = {}
        for rid, r in rooms.items():
            if r.mobs or r.items:
                room_states[rid] = room_state_snapshot(r)

        total_ticks = tick
        yield json.dumps({
            "type": "tick",
            "tick": tick,
            "events": [event_to_dict(e) for e in tick_events],
            "agent_states": agent_states,
            "room_states": room_states,
        }) + "\n"

        if check_boss_defeated(rooms):
            outcome = "victory"
            break

        if all_agents_dead(agents):
            outcome = "defeat"
            break

    log.info("Simulation complete: %s in %d ticks", outcome, total_ticks)
    yield json.dumps({"type": "done", "outcome": outcome, "total_ticks": total_ticks}) + "\n"


# ── API Endpoints ──────────────────────────────────────────────────────

@app.post("/api/simulate")
async def simulate():
    """Stream a simulation as newline-delimited JSON."""
    if LLM_BACKEND != "ollama" and not ANTHROPIC_API_KEY:
        raise HTTPException(
            status_code=500,
            detail="ANTHROPIC_API_KEY environment variable is not set. "
                   "Export it before starting the server: export ANTHROPIC_API_KEY=sk-...",
        )
    return StreamingResponse(simulation_stream(), media_type="application/x-ndjson")


@app.get("/api/world")
async def get_world():
    """Return the static world map."""
    world_file = os.path.join(PROJECT_ROOT, "data", "world.json")
    with open(world_file) as f:
        return json.load(f)


# ── Serve frontend static files ────────────────────────────────────────

FRONTEND_DIST = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")

if os.path.isdir(FRONTEND_DIST):
    app.mount("/assets", StaticFiles(directory=os.path.join(FRONTEND_DIST, "assets")), name="assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        """Serve the React SPA for any non-API route."""
        file_path = os.path.join(FRONTEND_DIST, full_path)
        if os.path.isfile(file_path):
            return FileResponse(file_path)
        return FileResponse(os.path.join(FRONTEND_DIST, "index.html"))
