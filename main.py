from __future__ import annotations

import sys

from agent import get_agent_action, get_agent_discussion, parse_action
from combat import (
    resolve_attack,
    resolve_fireball,
    resolve_heal,
    resolve_missile,
    resolve_poison,
    tick_poison,
)
from config import AGENT_TEMPLATES, MAX_TICKS
from memory import append_memory, build_narrative_memory, clear_memories
from models import AgentState, GameEvent, Item, Room
from narrator import narrate_combat, narrate_npc_dialogue
from world import build_sensory_context, build_world, describe_room

DIRECTION_NAMES = {"n": "north", "s": "south", "e": "east", "w": "west"}

# Force unbuffered output so the game can be watched live
_builtin_print = print


def print(*args, **kwargs):
    kwargs.setdefault("flush", True)
    _builtin_print(*args, **kwargs)


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


def resolve_action(
    agent: AgentState,
    cmd: str,
    arg: str,
    rooms: dict[str, Room],
    agents: list[AgentState],
    tick: int,
) -> list[GameEvent]:
    events = []
    room = rooms[agent.room_id]

    if cmd in ("n", "s", "e", "w"):
        if cmd in room.exits:
            old_room = room.name
            new_room_id = room.exits[cmd]
            agent.room_id = new_room_id
            new_room = rooms[new_room_id]
            # Generate description on first visit
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
        # First word is the target name, rest is the message
        parts = arg.split(None, 1)
        target_name = parts[0].lower() if parts else ""
        message = parts[1] if len(parts) > 1 else ""

        # Check NPCs
        npc = None
        for n in room.npcs:
            if target_name in n.name.lower():
                npc = n
                break
        if npc:
            dialogue = narrate_npc_dialogue(npc.name, npc.title, npc.dialogue, agent.name)
            result = f"{npc.name} says: {dialogue}"
            if npc.item and not npc.item_given:
                agent.inventory.append(npc.item)
                equip_item(agent, npc.item)
                result += f"\n  {npc.name} gives {agent.name} a {npc.item.name}!"
                npc.item_given = True
            events.append(GameEvent(tick, agent.name, f"tell {npc.name}", result, agent.room_id))
        else:
            # Check agents in the room
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
        # Normalize: "pick up X" -> arg="up X", strip the "up"
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


def equip_item(agent: AgentState, item: Item) -> None:
    if item.slot == "weapon" and item.atk > agent.weapon.atk:
        agent.weapon = item
    elif item.slot == "armor" and item.pdef > agent.armor.pdef:
        agent.armor = item
    elif item.slot == "ring" and item.mdmg > agent.ring.mdmg:
        agent.ring = item


def check_boss_defeated(rooms: dict[str, Room]) -> bool:
    for room in rooms.values():
        for mob in room.mobs:
            if mob.is_boss and mob.hp <= 0:
                return True
    return False


def all_agents_dead(agents: list[AgentState]) -> bool:
    return all(not a.alive for a in agents)


def print_tick_header(tick: int) -> None:
    print(f"\n{'═' * 40}")
    print(f"  TICK {tick}")
    print(f"{'═' * 40}\n")


def print_agent_events(agent: AgentState, events: list[GameEvent], rooms: dict[str, Room]) -> None:
    room = rooms[agent.room_id]
    print(f"[{agent.name} the {agent.agent_class}] in {room.name}")
    for e in events:
        if e.agent == agent.name or "counterattack" in e.action or e.agent == "poison":
            for line in e.result.split("\n"):
                print(f"  > {line}")
    print()


def main() -> None:
    print("=" * 50)
    print("  NachoMUD - Multi-Agent LLM Dungeon")
    print("  A Shadowfell Rift threatens Aeldrath...")
    print("=" * 50)
    print()

    # Build world
    rooms = build_world()

    # Print room map
    print("\n--- DUNGEON MAP ---")
    for room_id, room in sorted(rooms.items()):
        exits = ", ".join(f"{d}->{tid}" for d, tid in room.exits.items())
        mobs = ", ".join(m.name for m in room.mobs) if room.mobs else "none"
        npcs = ", ".join(n.name for n in room.npcs) if room.npcs else "none"
        print(f"  {room_id}: {room.name} | exits: {exits} | mobs: {mobs} | npcs: {npcs}")
    print("-------------------\n")

    # Create agents
    agents = create_agents()
    print("Heroes summoned:")
    for a in agents:
        print(f"  {a.name} the {a.agent_class} - HP:{a.hp}/{a.max_hp} MP:{a.mp}/{a.max_mp}")
    print()

    # Describe starting room
    start_room = rooms["room_1"]
    describe_room(start_room)
    print(f"Starting location: {start_room.name}")
    print(f"  {start_room.description}\n")

    # Game loop
    for tick in range(1, MAX_TICKS + 1):
        print_tick_header(tick)

        all_tick_events: list[GameEvent] = []

        # --- Discussion phase ---
        # Group agents by room so they discuss with allies present
        room_groups: dict[str, list[AgentState]] = {}
        for agent in agents:
            if agent.alive:
                room_groups.setdefault(agent.room_id, []).append(agent)

        # Each room has its own discussion
        room_discussions: dict[str, list[str]] = {}
        for room_id, room_agents in room_groups.items():
            room = rooms[room_id]
            others_map = {a.name: [o.name for o in room_agents if o.name != a.name] for a in room_agents}
            all_names = [a.name for a in room_agents]
            discussion: list[str] = []

            for agent in room_agents:
                sensory = build_sensory_context(room, all_names, rooms, agent.name)
                try:
                    utterance = get_agent_discussion(agent, sensory, others_map[agent.name], discussion)
                except Exception as e:
                    print(f"  [ERROR] {agent.name} discussion failed: {e}")
                    utterance = "Let's keep moving."
                discussion.append(f"{agent.name}: {utterance}")
                print(f"[{agent.name}] Says: {utterance}")

            room_discussions[room_id] = discussion
            # Record discussion as say events
            for agent in room_agents:
                line = next((d for d in discussion if d.startswith(f"{agent.name}:")), None)
                if line:
                    msg = line.split(":", 1)[1].strip()
                    all_tick_events.append(GameEvent(tick, agent.name, "say", f'{agent.name} says: "{msg}"', room_id))

        print()

        # --- Action phase (interleaved with results) ---
        # Track actions per room so agents see what happened before them
        room_actions: dict[str, list[str]] = {rid: [] for rid in room_discussions}

        for agent in agents:
            if not agent.alive:
                continue

            room = rooms[agent.room_id]
            others = agents_in_room(agents, agent.room_id, agent.name)
            sensory = build_sensory_context(room, [agent.name] + others, rooms, agent.name)
            discussion = room_discussions.get(agent.room_id, [])
            actions_so_far = room_actions.get(agent.room_id, [])

            # Get action from LLM
            try:
                action_str = get_agent_action(agent, sensory, discussion, actions_so_far)
            except Exception as e:
                print(f"  [ERROR] {agent.name} agent failed: {e}")
                action_str = "say I'm not sure what to do."

            cmd, arg = parse_action(action_str)
            print(f"[{agent.name}] Action: {action_str}")

            # Resolve action
            events = resolve_action(agent, cmd, arg, rooms, agents, tick)
            all_tick_events.extend(events)

            # Inject results into actions context for the next agent
            for e in events:
                room_actions.setdefault(agent.room_id, []).append(f"{e.agent}: {e.result.split(chr(10))[0]}")

            # Track last action for next turn's context
            agent.last_action = action_str
            agent.last_result = events[0].result.split("\n")[0] if events else ""

            # Print events
            print_agent_events(agent, events, rooms)

        # Poison ticks for all rooms with poisoned mobs
        for room in rooms.values():
            poison_events = tick_poison(room, tick)
            if poison_events:
                for e in poison_events:
                    print(f"  [Poison] {e.result}")
                all_tick_events.extend(poison_events)

        # Narrate notable events (boss fights, deaths)
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

        # Update memories
        for agent in agents:
            if not agent.alive:
                continue
            agent_events = [e for e in all_tick_events
                           if e.room_id == agent.room_id or e.agent == agent.name]
            if agent_events:
                room = rooms[agent.room_id]
                summary = build_narrative_memory(agent.name, agent_events, room.name)
                if summary:
                    append_memory(agent.name, tick, summary)

        # Check win/loss
        if check_boss_defeated(rooms):
            print("\n" + "=" * 50)
            print("  VICTORY! The Shadowfell Rift has been closed!")
            print("  The heroes of Aeldrath are triumphant!")
            print("=" * 50)
            survivors = [a for a in agents if a.alive]
            for a in survivors:
                print(f"  {a.name} the {a.agent_class} survived with {a.hp}/{a.max_hp} HP")
            fallen = [a for a in agents if not a.alive]
            for a in fallen:
                print(f"  {a.name} the {a.agent_class} fell in battle.")
            break

        if all_agents_dead(agents):
            print("\n" + "=" * 50)
            print("  DEFEAT! All heroes have fallen.")
            print("  The Shadowfell Rift consumes Aeldrath...")
            print("=" * 50)
            break
    else:
        print("\n" + "=" * 50)
        print(f"  TIME'S UP! {MAX_TICKS} ticks elapsed.")
        print("  The heroes could not close the rift in time.")
        print("=" * 50)

    print("\nGame over.")


if __name__ == "__main__":
    main()
