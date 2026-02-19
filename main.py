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
from config import ACTION_HISTORY_SIZE, AGENT_TEMPLATES, MAX_TICKS
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
        events.extend(resolve_attack(agent, room, arg, tick, agents))

    elif cmd == "missile":
        events.extend(resolve_missile(agent, room, arg, tick, agents))

    elif cmd == "fireball":
        events.extend(resolve_fireball(agent, room, tick))

    elif cmd == "poison":
        events.extend(resolve_poison(agent, room, arg, tick, agents))

    elif cmd == "heal":
        events.extend(resolve_heal(agent, tick, arg, agents, room))

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
            if npc.interactions_left > 0:
                npc.interactions_left -= 1
                dialogue = narrate_npc_dialogue(npc.name, npc.title, npc.dialogue, agent.name)
                result = f"{npc.name} says: {dialogue}"
                if npc.item and not npc.item_given:
                    agent.inventory.append(npc.item)
                    equip_item(agent, npc.item)
                    result += f"\n  {npc.name} gives {agent.name} a {npc.item.name}!"
                    npc.item_given = True
            else:
                result = f"{npc.name} has nothing more to say."
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
                others = agents_in_room(agents, agent.room_id, agent.name)
                npcs_here = [n.name for n in room.npcs]
                available = others + npcs_here
                if available:
                    result = f"No one named '{target_name}' here. You can talk to: {', '.join(available)}."
                else:
                    result = f"No one named '{target_name}' here. There is nobody to talk to in this room."
                events.append(GameEvent(tick, agent.name, f"tell {target_name}", result, agent.room_id))

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
            available = [i.name for i in room.items]
            if available:
                result = f"No item named '{arg}' here. Items available: {', '.join(available)}."
            else:
                result = f"No item named '{arg}' here. There are no items to pick up in this room."
            events.append(GameEvent(tick, agent.name, f"get {arg}", result, agent.room_id))

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

    # ── Round 0: one-time planning discussion ──
    print("\n--- ROUND 0: PLANNING ---")
    round0_plan: list[str] = []
    all_names = [a.name for a in agents]

    for agent in agents:
        others = [a.name for a in agents if a.name != agent.name]
        sensory = build_sensory_context(start_room, all_names, rooms, agent.name)
        try:
            utterance = get_agent_discussion(agent, sensory, others, round0_plan)
        except Exception as e:
            print(f"  [ERROR] {agent.name} discussion failed: {e}")
            utterance = "Let's keep moving."
        round0_plan.append(f"{agent.name}: {utterance}")
        print(f"[{agent.name}] Says: {utterance}")

    print()

    # Seed action_history with round-0 discussion for all agents
    for plan_line in round0_plan:
        for agent in agents:
            agent.action_history.append(plan_line)

    def _witness(event_text: str, room_id: str, acting_agent_name: str = "") -> None:
        """Append an event to action_history of all agents in the given room."""
        for a in agents:
            if a.alive and a.room_id == room_id:
                if a.name == acting_agent_name:
                    a.action_history.append(f">> {event_text}")
                else:
                    a.action_history.append(event_text)
                a.action_history = a.action_history[-ACTION_HISTORY_SIZE:]

    for tick in range(1, MAX_TICKS + 1):
        print_tick_header(tick)

        all_tick_events: list[GameEvent] = []

        for agent in agents:
            if not agent.alive:
                continue

            room = rooms[agent.room_id]
            others = agents_in_room(agents, agent.room_id, agent.name)
            sensory = build_sensory_context(room, [agent.name] + others, rooms, agent.name)

            # Get action from LLM
            try:
                think, action_str = get_agent_action(agent, sensory, room=room, allies=agents)
            except Exception as e:
                print(f"  [ERROR] {agent.name} agent failed: {e}")
                think, action_str = "", "say I'm not sure what to do."

            cmd, arg = parse_action(action_str)
            if think:
                print(f"[{agent.name}] Think: {think}")
            print(f"[{agent.name}] Action: {action_str}")

            # Track the room the agent is in BEFORE the action (for witnessing)
            pre_action_room = agent.room_id

            # Resolve action
            events = resolve_action(agent, cmd, arg, rooms, agents, tick)
            all_tick_events.extend(events)

            # Track last action
            agent.last_action = action_str
            agent.last_result = events[0].result.split("\n")[0] if events else ""

            # Witnessed events: everyone in the room sees the result
            for e in events:
                result_line = e.result.split("\n")[0]
                if "moves" in e.action:
                    # Old room: others see departure (agent already moved, won't match)
                    _witness(f"{agent.name} leaves heading {DIRECTION_NAMES.get(cmd, cmd)}", pre_action_room)
                    # New room: others see arrival from the opposite direction
                    opposite = {"n": "south", "s": "north", "e": "west", "w": "east"}
                    arrival_dir = opposite.get(cmd, "somewhere")
                    for a in agents:
                        if a.alive and a.room_id == agent.room_id and a.name != agent.name:
                            a.action_history.append(f"{agent.name} arrives from the {arrival_dir}")
                            a.action_history = a.action_history[-ACTION_HISTORY_SIZE:]
                    # Moving agent: own action
                    agent.action_history.append(f">> {action_str} → {result_line}")
                    agent.action_history = agent.action_history[-ACTION_HISTORY_SIZE:]
                else:
                    _witness(result_line, agent.room_id, agent.name)

            # Print events
            print_agent_events(agent, events, rooms)


        # Poison ticks for all rooms with poisoned mobs
        for room in rooms.values():
            poison_events = tick_poison(room, tick)
            if poison_events:
                for e in poison_events:
                    print(f"  [Poison] {e.result}")
                    _witness(e.result, e.room_id)
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
