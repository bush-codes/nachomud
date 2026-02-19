"""FastAPI backend for NachoMUD web visualization."""
from __future__ import annotations

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

from agent import get_agent_action, get_agent_comm, parse_action
from effects import tick_effects
from mob_ai import get_mob_action, get_mob_comm, resolve_mob_ability
import config
from config import ACTION_HISTORY_SIZE, ANTHROPIC_API_KEY, CLASS_DEFINITIONS, COMM_HISTORY_SIZE, LLM_BACKEND, LORE_HISTORY_SIZE, MAX_TICKS
from engine import (
    agents_in_room,
    all_agents_dead,
    build_initiative_order,
    check_boss_defeated,
    create_agents,
    regen_warrior_ap,
    resolve_action,
    witness,
    witness_events,
)
from models import AgentState, GameEvent, Item, Mob, Room
from world import build_sensory_context, build_world, describe_room, list_worlds

log = logging.getLogger("nachomud")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

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
        "agent_class": agent.agent_class,
        "hp": agent.hp,
        "max_hp": agent.max_hp,
        "mp": agent.mp,
        "max_mp": agent.max_mp,
        "ap": agent.ap,
        "max_ap": agent.max_ap,
        "speed": agent.speed,
        "room_id": agent.room_id,
        "alive": agent.alive,
        "weapon": item_to_dict(agent.weapon),
        "armor": item_to_dict(agent.armor),
        "ring": item_to_dict(agent.ring),
        "last_action": agent.last_action,
        "last_result": agent.last_result,
        "status_effects": [
            {"name": se.name, "remaining_ticks": se.remaining_ticks, "value": se.value}
            for se in agent.status_effects
        ],
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


def _build_state_snapshots(agents, rooms):
    """Build agent and room state snapshots for streaming."""
    agent_states = [agent_state_snapshot(a) for a in agents]
    room_states = {}
    for rid, r in rooms.items():
        if r.mobs or r.items:
            room_states[rid] = room_state_snapshot(r)
    return agent_states, room_states


# ── Simulation runner (streaming) ──────────────────────────────────────

def simulation_stream(max_ticks: int = MAX_TICKS, agent_model: str | None = None, world_id: str = "shadowfell", party: list[str] | None = None) -> Generator[str, None, None]:
    """Sync generator that yields newline-delimited JSON: init, tick*, done."""
    from datetime import datetime

    if agent_model:
        config.AGENT_MODEL = agent_model

    rooms = build_world(world_id)
    describe_room(rooms["room_1"])
    agents = create_agents(party)
    for a in agents:
        a.visited_rooms.append(rooms["room_1"].name)
    log.info("Simulation started: %d agents, %d max ticks, model=%s, party=%s", len(agents), max_ticks, config.AGENT_MODEL, [a.agent_class for a in agents])

    # Open a log file for this run
    log_dir = os.path.join(PROJECT_ROOT, "data", "logs")
    os.makedirs(log_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = os.path.join(log_dir, f"sim_{timestamp}.log")
    sim_log = open(log_path, "w")
    log.info("Simulation log: %s", log_path)

    def slog(text: str) -> None:
        sim_log.write(text + "\n")
        sim_log.flush()

    slog(f"=== NachoMUD Simulation - {timestamp} ===")
    slog(f"Agents: {', '.join(a.name + ' the ' + a.agent_class for a in agents)}")
    slog(f"Max ticks: {max_ticks}")
    slog("")

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

    for tick in range(1, max_ticks + 1):
        slog(f"{'=' * 50}")
        slog(f"  TICK {tick}")
        slog(f"{'=' * 50}")
        tick_events = []

        # Build initiative order
        initiative = build_initiative_order(agents, rooms)
        agent_order = [e for e in initiative if isinstance(e, AgentState)]
        mob_order = [e for e in initiative if isinstance(e, Mob)]

        # ── Communication phase (agents) ──
        slog(f"  --- COMM PHASE ---")
        for agent in agent_order:

            room = rooms[agent.room_id]
            others = agents_in_room(agents, agent.room_id, agent.name)
            sensory = build_sensory_context(room, [agent.name] + others, rooms, agent.name, agent.visited_rooms, agent_class=agent.agent_class)

            try:
                comm_think, comm_action = get_agent_comm(agent, sensory, others, room=room, allies=agents)
            except Exception as e:
                log.error("Tick %d: %s comm failed: %s", tick, agent.name, e)
                comm_think, comm_action = "", None

            slog(f"  [{agent.name}] Comm Think: {comm_think}")

            # Stream comm think to frontend
            if comm_think:
                think_event = GameEvent(tick, agent.name, "think", f'{agent.name} thinks: "{comm_think}"', agent.room_id)
                tick_events.append(think_event)
                agent_states, room_states_snap = _build_state_snapshots(agents, rooms)
                yield json.dumps({"type": "event", "tick": tick, "event": event_to_dict(think_event), "agent_states": agent_states, "room_states": room_states_snap}) + "\n"

            if comm_action is None:
                slog(f"  [{agent.name}] Comm: (silent)")
                continue

            log.info("Tick %d: %s comm: %s", tick, agent.name, comm_action)
            slog(f"  [{agent.name}] Comm: {comm_action}")

            cmd, arg = parse_action(comm_action)
            pre_action_room = agent.room_id
            events = resolve_action(agent, cmd, arg, rooms, agents, tick)

            for e in events:
                tick_events.append(e)
                for line in e.result.split("\n"):
                    slog(f"    > {line}")
                agent_states, room_states_snap = _build_state_snapshots(agents, rooms)
                yield json.dumps({"type": "event", "tick": tick, "event": event_to_dict(e), "agent_states": agent_states, "room_states": room_states_snap}) + "\n"

            witness_events(agents, rooms, events, agent, cmd, arg, comm_action, pre_action_room)

        # ── Mob comm phase ──
        for mob in mob_order:
            if mob.hp <= 0:
                continue
            room = rooms.get(mob.room_id)
            if not room:
                continue
            try:
                comm = get_mob_comm(mob, room, agents)
            except Exception as e:
                log.error("Tick %d: %s mob comm failed: %s", tick, mob.name, e)
                continue

            if comm:
                slog(f"  [{mob.name}] says: \"{comm}\"")
                event = GameEvent(tick, mob.name, "say", f'{mob.name} says: "{comm}"', mob.room_id, category="comm")
                tick_events.append(event)
                witness(agents, event.result, mob.room_id, history="comm")
                agent_states, room_states_snap = _build_state_snapshots(agents, rooms)
                yield json.dumps({"type": "event", "tick": tick, "event": event_to_dict(event), "agent_states": agent_states, "room_states": room_states_snap}) + "\n"

        # ── Action phase (interleaved agents + mobs in speed order) ──
        slog(f"  --- ACTION PHASE ---")
        for entity in initiative:
            if isinstance(entity, AgentState):
                agent = entity
                if not agent.alive:
                    continue

                room = rooms[agent.room_id]
                others = agents_in_room(agents, agent.room_id, agent.name)
                sensory = build_sensory_context(room, [agent.name] + others, rooms, agent.name, agent.visited_rooms, agent_class=agent.agent_class)

                # Log full agent context for debugging
                slog(f"  [{agent.name}] --- Context ---")
                for line in sensory.split("\n"):
                    slog(f"    | {line}")
                if agent.action_history:
                    slog(f"    | Recent events:")
                    for entry in agent.action_history[-ACTION_HISTORY_SIZE:]:
                        slog(f"    |   {entry}")
                if agent.comm_history:
                    slog(f"    | Ally comms:")
                    for entry in agent.comm_history[-COMM_HISTORY_SIZE:]:
                        slog(f"    |   {entry}")
                if agent.lore_history:
                    slog(f"    | NPC lore:")
                    for entry in agent.lore_history[-LORE_HISTORY_SIZE:]:
                        slog(f"    |   {entry}")

                try:
                    think, action_str, retries = get_agent_action(agent, sensory, room=room, allies=agents)
                except Exception as e:
                    log.error("Tick %d: %s agent API call failed: %s", tick, agent.name, e)
                    think, action_str, retries = "", "say I'm not sure what to do.", []

                cmd, arg = parse_action(action_str)
                log.info("Tick %d: %s thinks: %s -> %s", tick, agent.name, think, action_str)

                pre_action_room = agent.room_id

                events = resolve_action(agent, cmd, arg, rooms, agents, tick)

                agent.last_action = action_str
                agent.last_result = events[0].result.split("\n")[0] if events else ""

                if events and events[0].action.startswith("move"):
                    new_room = rooms[agent.room_id]
                    if new_room.name not in agent.visited_rooms:
                        agent.visited_rooms.append(new_room.name)

                slog(f"  [{agent.name}] Think: {think}")
                for r in retries:
                    slog(f"  [{agent.name}] Retry: '{r}' was invalid")
                slog(f"  [{agent.name}] Action: {action_str}")

                # Stream think as a separate event
                if think:
                    think_event = GameEvent(tick, agent.name, "think", f'{agent.name} thinks: "{think}"', agent.room_id)
                    tick_events.append(think_event)
                    agent_states, room_states_snap = _build_state_snapshots(agents, rooms)
                    yield json.dumps({"type": "event", "tick": tick, "event": event_to_dict(think_event), "agent_states": agent_states, "room_states": room_states_snap}) + "\n"

                for e in events:
                    tick_events.append(e)
                    for line in e.result.split("\n"):
                        slog(f"    > {line}")
                    agent_states, room_states_snap = _build_state_snapshots(agents, rooms)
                    yield json.dumps({"type": "event", "tick": tick, "event": event_to_dict(e), "agent_states": agent_states, "room_states": room_states_snap}) + "\n"

                witness_events(agents, rooms, events, agent, cmd, arg, action_str, pre_action_room)

            elif isinstance(entity, Mob):
                mob = entity
                if mob.hp <= 0:
                    continue
                room = rooms.get(mob.room_id)
                if not room:
                    continue

                try:
                    cmd, arg = get_mob_action(mob, room, agents, rooms, tick)
                except Exception as e:
                    log.error("Tick %d: %s mob action failed: %s", tick, mob.name, e)
                    continue

                if not cmd:
                    continue  # mob skipped (asleep, no targets, etc.)

                slog(f"  [{mob.name}] Action: {cmd} {arg}")

                events = resolve_mob_ability(mob, cmd, arg, room, tick, agents)

                for e in events:
                    tick_events.append(e)
                    for line in e.result.split("\n"):
                        slog(f"    > {line}")
                    witness(agents, e.result, mob.room_id)
                    agent_states, room_states_snap = _build_state_snapshots(agents, rooms)
                    yield json.dumps({"type": "event", "tick": tick, "event": event_to_dict(e), "agent_states": agent_states, "room_states": room_states_snap}) + "\n"

        # Effect ticks (DoTs, buff expiry) for all agents and mobs
        for agent in agents:
            if agent.alive:
                effect_events = tick_effects(agent, tick, agent.room_id)
                for e in effect_events:
                    tick_events.append(e)
                    slog(f"  [Effect] {e.result}")
                    witness(agents, e.result, e.room_id)
                    agent_states, room_states_snap = _build_state_snapshots(agents, rooms)
                    yield json.dumps({"type": "event", "tick": tick, "event": event_to_dict(e), "agent_states": agent_states, "room_states": room_states_snap}) + "\n"
        for room in rooms.values():
            for mob in room.mobs:
                if mob.hp > 0:
                    effect_events = tick_effects(mob, tick, room.id)
                    for e in effect_events:
                        tick_events.append(e)
                        slog(f"  [Effect] {e.result}")
                        witness(agents, e.result, room.id)
                        agent_states, room_states_snap = _build_state_snapshots(agents, rooms)
                        yield json.dumps({"type": "event", "tick": tick, "event": event_to_dict(e), "agent_states": agent_states, "room_states": room_states_snap}) + "\n"

        # AP regeneration for Warriors
        regen_warrior_ap(agents)

        # Snapshot state
        agent_states, room_states = _build_state_snapshots(agents, rooms)

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

    slog("")
    slog(f"{'=' * 50}")
    slog(f"  RESULT: {outcome.upper()} after {total_ticks} ticks")
    slog(f"{'=' * 50}")
    for a in agents:
        status = f"HP:{a.hp}/{a.max_hp} MP:{a.mp}/{a.max_mp} in {a.room_id}" if a.alive else "FALLEN"
        slog(f"  {a.name} the {a.agent_class}: {status}")
    sim_log.close()

    log.info("Simulation complete: %s in %d ticks", outcome, total_ticks)
    log.info("Full log written to: %s", log_path)
    yield json.dumps({"type": "done", "outcome": outcome, "total_ticks": total_ticks}) + "\n"


# ── API Endpoints ──────────────────────────────────────────────────────

@app.post("/api/simulate")
async def simulate(max_ticks: int = MAX_TICKS, agent_model: str | None = None, world_id: str = "shadowfell", party: str | None = None):
    """Stream a simulation as newline-delimited JSON.

    party: comma-separated class names (e.g., "Warrior,Mage,Cleric"). Max 3.
    """
    if LLM_BACKEND != "ollama" and not ANTHROPIC_API_KEY:
        raise HTTPException(
            status_code=500,
            detail="ANTHROPIC_API_KEY environment variable is not set. "
                   "Export it before starting the server: export ANTHROPIC_API_KEY=sk-...",
        )
    ticks = max(1, min(max_ticks, 200))
    party_list = None
    if party:
        party_list = [c.strip() for c in party.split(",") if c.strip() in CLASS_DEFINITIONS]
        if not party_list:
            party_list = None
    return StreamingResponse(simulation_stream(ticks, agent_model, world_id, party_list), media_type="application/x-ndjson")


@app.get("/api/classes")
async def get_classes():
    """Return class definitions for the party selector UI."""
    return {
        name: {
            "hp": cls["hp"],
            "resource_type": cls["resource_type"],
            "resource_max": cls["resource_max"],
            "speed": cls["speed"],
            "abilities": cls["abilities"],
            "default_name": cls["default_name"],
            "personality": cls["personality"],
        }
        for name, cls in CLASS_DEFINITIONS.items()
    }


@app.get("/api/worlds")
async def get_worlds():
    """Return the list of available worlds."""
    return list_worlds()


@app.get("/api/world")
async def get_world(world_id: str = "shadowfell"):
    """Return a specific world map."""
    world_file = os.path.join(PROJECT_ROOT, "data", "worlds", f"{world_id}.json")
    if not os.path.exists(world_file):
        world_file = os.path.join(PROJECT_ROOT, "data", "world.json")
    if not os.path.exists(world_file):
        raise HTTPException(status_code=404, detail=f"World '{world_id}' not found")
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
