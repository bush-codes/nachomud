from __future__ import annotations

import argparse
import json
import os
from datetime import datetime

import config
from agent import get_agent_action, get_agent_comm, parse_action
from effects import tick_effects
from engine import (
    agents_in_room,
    all_agents_dead,
    build_initiative_order,
    check_boss_defeated,
    create_agents,
    regen_warrior_ap,
    resolve_action,
    witness_events,
    witness,
)
from mob_ai import get_mob_action, get_mob_comm, resolve_mob_ability
from models import AgentState, GameEvent, Mob
from narrator import narrate_combat
from world import build_sensory_context, build_world, describe_room

# Force unbuffered output so the game can be watched live
_builtin_print = print


def print(*args, **kwargs):
    kwargs.setdefault("flush", True)
    _builtin_print(*args, **kwargs)


def print_tick_header(tick: int) -> None:
    print(f"\n{'═' * 40}")
    print(f"  TICK {tick}")
    print(f"{'═' * 40}\n")


# ── JSON log helpers ──────────────────────────────────────────────────

def _agent_snapshot(agent: AgentState) -> dict:
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
        "weapon": agent.weapon.name,
        "armor": agent.armor.name,
        "ring": agent.ring.name,
        "status_effects": [
            {"name": se.name, "remaining_ticks": se.remaining_ticks, "value": se.value}
            for se in agent.status_effects
        ],
    }


def _event_to_dict(event: GameEvent) -> dict:
    return {
        "agent": event.agent,
        "action": event.action,
        "result": event.result,
        "room_id": event.room_id,
        "category": event.category,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="NachoMUD - AI Dungeon Crawler")
    parser.add_argument("--world", default="shadowfell",
                        help="World ID (shadowfell, frostpeak, serpentmire, emberhollows)")
    parser.add_argument("--model", default=None,
                        help="LLM model override (e.g. gemma3:4b, gemma3:12b)")
    parser.add_argument("--max-ticks", type=int, default=config.MAX_TICKS,
                        help=f"Max simulation ticks (default: {config.MAX_TICKS})")
    parser.add_argument("--party", default="Warrior,Mage,Ranger",
                        help="Comma-separated class names, max 3 (default: Warrior,Mage,Ranger)")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    # Override config before game loop
    if args.model:
        config.AGENT_MODEL = args.model
    max_ticks = args.max_ticks
    party_list = [c.strip() for c in args.party.split(",") if c.strip() in config.CLASS_DEFINITIONS]
    if not party_list:
        party_list = ["Warrior", "Mage", "Ranger"]

    print("=" * 50)
    print("  NachoMUD - Multi-Agent LLM Dungeon")
    print(f"  World: {args.world} | Model: {config.AGENT_MODEL} | Ticks: {max_ticks}")
    print(f"  Party: {', '.join(party_list)}")
    print("=" * 50)
    print()

    rooms = build_world(args.world)

    print("\n--- DUNGEON MAP ---")
    for room_id, room in sorted(rooms.items()):
        exits = ", ".join(f"{d}->{tid}" for d, tid in room.exits.items())
        mobs = ", ".join(m.name for m in room.mobs) if room.mobs else "none"
        npcs = ", ".join(n.name for n in room.npcs) if room.npcs else "none"
        print(f"  {room_id}: {room.name} | exits: {exits} | mobs: {mobs} | npcs: {npcs}")
    print("-------------------\n")

    agents = create_agents(party_list)
    print("Heroes summoned:")
    for a in agents:
        resource = f"AP:{a.ap}/{a.max_ap}" if a.agent_class == "Warrior" else f"MP:{a.mp}/{a.max_mp}"
        print(f"  {a.name} the {a.agent_class} - HP:{a.hp}/{a.max_hp} {resource} SPD:{a.speed}")
    print()

    start_room = rooms["room_1"]
    describe_room(start_room)
    for a in agents:
        a.visited_rooms.append(start_room.name)
    print(f"Starting location: {start_room.name}")
    print(f"  {start_room.description}\n")

    # ── JSON log setup ────────────────────────────────────────────────
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    sim_log = {
        "meta": {
            "timestamp": timestamp,
            "world_id": args.world,
            "model": config.AGENT_MODEL,
            "max_ticks": max_ticks,
            "party": party_list,
            "outcome": "timeout",
            "total_ticks": 0,
        },
        "agents_initial": [_agent_snapshot(a) for a in agents],
        "ticks": [],
        "final_agent_states": [],
    }

    outcome = "timeout"

    for tick in range(1, max_ticks + 1):
        print_tick_header(tick)

        all_tick_events: list[GameEvent] = []
        tick_log: dict = {
            "tick": tick,
            "comm_phase": [],
            "mob_comms": [],
            "action_phase": [],
            "effect_events": [],
            "agent_states_end": [],
        }

        # Build initiative order
        initiative = build_initiative_order(agents, rooms)
        agent_order = [e for e in initiative if isinstance(e, AgentState)]
        mob_order = [e for e in initiative if isinstance(e, Mob)]

        # ── Communication phase (agents + mob bosses) ──
        for agent in agent_order:
            room = rooms[agent.room_id]
            others = agents_in_room(agents, agent.room_id, agent.name)
            sensory = build_sensory_context(room, [agent.name] + others, rooms, agent.name, agent.visited_rooms, agent_class=agent.agent_class)

            try:
                comm_think, comm_action = get_agent_comm(agent, sensory, others, room=room, allies=agents)
            except Exception as e:
                print(f"  [ERROR] {agent.name} comm failed: {e}")
                continue

            if comm_think:
                print(f"[{agent.name}] Comm Think: {comm_think}")

            if comm_action is None:
                print(f"[{agent.name}] Comm: (silent)")
                tick_log["comm_phase"].append({
                    "agent": agent.name,
                    "think": comm_think or "",
                    "action": None,
                    "result": None,
                })
                continue

            print(f"[{agent.name}] Comm: {comm_action}")

            cmd, arg = parse_action(comm_action)
            pre_action_room = agent.room_id
            events = resolve_action(agent, cmd, arg, rooms, agents, tick)
            all_tick_events.extend(events)

            witness_events(agents, rooms, events, agent, cmd, arg, comm_action, pre_action_room)

            result_text = "; ".join(e.result for e in events) if events else ""
            tick_log["comm_phase"].append({
                "agent": agent.name,
                "think": comm_think or "",
                "action": comm_action,
                "result": result_text,
            })

            for e in events:
                for line in e.result.split("\n"):
                    print(f"  > {line}")
            print()

        # Mob comm phase
        for mob in mob_order:
            if mob.hp <= 0:
                continue
            room = rooms.get(mob.room_id)
            if not room:
                continue
            try:
                comm = get_mob_comm(mob, room, agents)
            except Exception as e:
                print(f"  [ERROR] {mob.name} comm failed: {e}")
                continue

            if comm:
                print(f"[{mob.name}] says: \"{comm}\"")
                event = GameEvent(tick, mob.name, "say", f'{mob.name} says: "{comm}"', mob.room_id, category="comm")
                all_tick_events.append(event)
                witness(agents, event.result, mob.room_id, history="comm")
                tick_log["mob_comms"].append({"mob": mob.name, "text": comm})

        # ── Action phase (interleaved agents + mobs in speed order) ──
        for entity in initiative:
            if isinstance(entity, AgentState):
                if not entity.alive:
                    continue
                agent = entity
                room = rooms[agent.room_id]
                others = agents_in_room(agents, agent.room_id, agent.name)
                sensory = build_sensory_context(room, [agent.name] + others, rooms, agent.name, agent.visited_rooms, agent_class=agent.agent_class)

                hp_before = agent.hp

                try:
                    think, action_str, retries = get_agent_action(agent, sensory, room=room, allies=agents)
                except Exception as e:
                    print(f"  [ERROR] {agent.name} agent failed: {e}")
                    think, action_str, retries = "", "say I'm not sure what to do.", []

                cmd, arg = parse_action(action_str)
                if think:
                    print(f"[{agent.name}] Think: {think}")
                for r in retries:
                    print(f"[{agent.name}] Retry: '{r}' was invalid")
                print(f"[{agent.name}] Action: {action_str}")

                pre_action_room = agent.room_id

                events = resolve_action(agent, cmd, arg, rooms, agents, tick)
                all_tick_events.extend(events)

                agent.last_action = action_str
                agent.last_result = events[0].result.split("\n")[0] if events else ""

                if events and events[0].action.startswith("move"):
                    new_room = rooms[agent.room_id]
                    if new_room.name not in agent.visited_rooms:
                        agent.visited_rooms.append(new_room.name)

                witness_events(agents, rooms, events, agent, cmd, arg, action_str, pre_action_room)

                room = rooms[agent.room_id]
                print(f"[{agent.name} the {agent.agent_class}] in {room.name}")
                for e in events:
                    if e.agent == agent.name or e.agent == "poison":
                        for line in e.result.split("\n"):
                            print(f"  > {line}")
                print()

                result_text = "; ".join(e.result for e in events) if events else ""
                tick_log["action_phase"].append({
                    "entity_type": "agent",
                    "name": agent.name,
                    "agent_class": agent.agent_class,
                    "room_id": agent.room_id,
                    "think": think or "",
                    "action": action_str,
                    "cmd": cmd,
                    "arg": arg or "",
                    "retries": retries,
                    "result": result_text,
                    "hp_before": hp_before,
                    "hp_after": agent.hp,
                })

            elif isinstance(entity, Mob):
                mob = entity
                if mob.hp <= 0:
                    continue
                room = rooms.get(mob.room_id)
                if not room:
                    continue

                hp_before = mob.hp

                try:
                    cmd, arg = get_mob_action(mob, room, agents, rooms, tick)
                except Exception as e:
                    print(f"  [ERROR] {mob.name} action failed: {e}")
                    continue

                if not cmd:
                    continue  # mob skipped (asleep, no targets, etc.)

                print(f"[{mob.name}] Action: {cmd} {arg}")

                events = resolve_mob_ability(mob, cmd, arg, room, tick, agents)
                all_tick_events.extend(events)

                for e in events:
                    for line in e.result.split("\n"):
                        print(f"  > {line}")
                    # Witness mob actions to agents in the room
                    witness(agents, e.result, mob.room_id)
                print()

                result_text = "; ".join(e.result for e in events) if events else ""
                tick_log["action_phase"].append({
                    "entity_type": "mob",
                    "name": mob.name,
                    "room_id": mob.room_id,
                    "cmd": cmd,
                    "arg": arg or "",
                    "result": result_text,
                    "hp_before": hp_before,
                    "hp_after": mob.hp,
                })

        # Effect ticks (DoTs, buff expiry) for all agents and mobs
        for agent in agents:
            if agent.alive:
                effect_events = tick_effects(agent, tick, agent.room_id)
                for e in effect_events:
                    print(f"  [Effect] {e.result}")
                    witness(agents, e.result, e.room_id)
                    tick_log["effect_events"].append({
                        "agent": e.agent,
                        "result": e.result,
                        "room_id": e.room_id,
                    })
                all_tick_events.extend(effect_events)
        for room in rooms.values():
            for mob in room.mobs:
                if mob.hp > 0:
                    effect_events = tick_effects(mob, tick, room.id)
                    for e in effect_events:
                        print(f"  [Effect] {e.result}")
                        witness(agents, e.result, room.id)
                        tick_log["effect_events"].append({
                            "agent": e.agent,
                            "result": e.result,
                            "room_id": room.id,
                        })
                    all_tick_events.extend(effect_events)

        # AP regeneration for Warriors
        regen_warrior_ap(agents)

        # Snapshot agent states at end of tick
        tick_log["agent_states_end"] = [_agent_snapshot(a) for a in agents]
        sim_log["ticks"].append(tick_log)

        # Narrate notable events
        for event in all_tick_events:
            is_notable = (
                "slain" in event.result.lower()
                or "fallen" in event.result.lower()
                or "boss" in event.action.lower()
            )
            if is_notable and event.agent != "poison":
                try:
                    narration = narrate_combat(event.agent, event.action, event.result)
                    print(f"  * {narration}")
                except Exception:
                    pass

        sim_log["meta"]["total_ticks"] = tick

        if check_boss_defeated(rooms):
            outcome = "victory"
            print("\n" + "=" * 50)
            print("  VICTORY! The boss has been defeated!")
            print("  The heroes are triumphant!")
            print("=" * 50)
            survivors = [a for a in agents if a.alive]
            for a in survivors:
                print(f"  {a.name} the {a.agent_class} survived with {a.hp}/{a.max_hp} HP")
            fallen = [a for a in agents if not a.alive]
            for a in fallen:
                print(f"  {a.name} the {a.agent_class} fell in battle.")
            break

        if all_agents_dead(agents):
            outcome = "defeat"
            print("\n" + "=" * 50)
            print("  DEFEAT! All heroes have fallen.")
            print("  The dungeon claims another party...")
            print("=" * 50)
            break
    else:
        print("\n" + "=" * 50)
        print(f"  TIME'S UP! {max_ticks} ticks elapsed.")
        print("  The heroes could not complete their quest in time.")
        print("=" * 50)

    # ── Write JSON log ────────────────────────────────────────────────
    sim_log["meta"]["outcome"] = outcome
    sim_log["final_agent_states"] = [
        {**_agent_snapshot(a), "visited_rooms": list(a.visited_rooms)}
        for a in agents
    ]

    log_dir = os.path.join("data", "logs")
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, f"sim_{timestamp}.json")
    with open(log_path, "w") as f:
        json.dump(sim_log, f, indent=2)

    print(f"\nJSON log: {log_path}")
    print("Game over.")


if __name__ == "__main__":
    main()
