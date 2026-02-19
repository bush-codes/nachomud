"""Core game engine — shared logic between CLI and web server."""
from __future__ import annotations

from collections import deque

from abilities import ABILITY_REGISTRY, resolve_ability
from config import (
    ABILITY_DEFINITIONS,
    ACTION_HISTORY_SIZE,
    AGENT_TEMPLATES,
    CLASS_DEFINITIONS,
    COMM_HISTORY_SIZE,
    LORE_HISTORY_SIZE,
)
from models import AgentState, GameEvent, Item, Mob, Room
from narrator import narrate_npc_dialogue, summarize_npc_dialogue
from world import describe_room

# AP regeneration rate for Warriors (per tick)
WARRIOR_AP_REGEN = 3

DIRECTION_NAMES = {"n": "north", "s": "south", "e": "east", "w": "west"}
OPPOSITE_DIRECTION = {"n": "south", "s": "north", "e": "west", "w": "east"}


def rooms_within_range(
    start_room_id: str, rooms: dict[str, Room], max_hops: int = 3
) -> dict[str, tuple[int, str]]:
    """BFS from start_room_id, returning {room_id: (distance, direction_from)}.

    direction_from is the direction the yell came FROM (opposite of the exit
    taken), so an adjacent room to the north gets direction_from="south"
    meaning the yell came from the south.
    """
    visited: dict[str, tuple[int, str]] = {start_room_id: (0, "")}
    queue: deque[str] = deque([start_room_id])
    while queue:
        current = queue.popleft()
        dist, _ = visited[current]
        if dist >= max_hops:
            continue
        room = rooms[current]
        for direction, neighbor_id in room.exits.items():
            if neighbor_id not in visited:
                from_dir = OPPOSITE_DIRECTION.get(direction, direction)
                visited[neighbor_id] = (dist + 1, from_dir)
                queue.append(neighbor_id)
    return visited


def create_agents(party: list[str] | None = None) -> list[AgentState]:
    """Create agents from CLASS_DEFINITIONS.

    party: list of class names (e.g., ["Warrior", "Mage", "Ranger"]).
           Defaults to ["Warrior", "Mage", "Ranger"] for backwards compat.
    """
    if party is None:
        party = ["Warrior", "Mage", "Ranger"]

    agents = []
    for class_name in party:
        cls = CLASS_DEFINITIONS.get(class_name)
        if not cls:
            continue

        hp = cls["hp"]
        if cls["resource_type"] == "ap":
            mp, max_mp = 0, 0
            ap, max_ap = cls["resource_max"], cls["resource_max"]
        else:
            mp, max_mp = cls["resource_max"], cls["resource_max"]
            ap, max_ap = 0, 0

        agent = AgentState(
            name=cls["default_name"],
            personality=cls["personality"],
            agent_class=class_name,
            hp=hp,
            max_hp=hp,
            mp=mp,
            max_mp=max_mp,
            weapon=Item(**cls["weapon"]),
            armor=Item(**cls["armor"]),
            ring=Item(**cls["ring"]),
            room_id="room_1",
            ap=ap,
            max_ap=max_ap,
            speed=cls["speed"],
        )
        agents.append(agent)
    return agents


def agents_in_room(
    agents: list[AgentState], room_id: str, exclude: str = ""
) -> list[str]:
    return [
        a.name for a in agents if a.alive and a.room_id == room_id and a.name != exclude
    ]


def build_initiative_order(
    agents: list[AgentState], rooms: dict[str, Room]
) -> list[AgentState | Mob]:
    """Build turn order sorted by speed descending.

    Ties broken: agents before mobs, then alphabetical by name.
    Only includes living entities.
    """
    entities: list[AgentState | Mob] = []
    for a in agents:
        if a.alive:
            entities.append(a)
    for room in rooms.values():
        for m in room.mobs:
            if m.hp > 0:
                entities.append(m)
    # Sort: speed descending, then agents before mobs, then alphabetical
    entities.sort(key=lambda e: (-e.speed, isinstance(e, Mob), e.name))
    return entities


def regen_warrior_ap(agents: list[AgentState]) -> None:
    """Regenerate AP for Warriors at end of tick."""
    for a in agents:
        if a.alive and a.agent_class == "Warrior" and a.max_ap > 0:
            a.ap = min(a.max_ap, a.ap + WARRIOR_AP_REGEN)


def can_equip(agent: AgentState, item: Item) -> bool:
    """Check if agent's class can equip this item."""
    if item.allowed_classes is None:
        return True  # unrestricted
    return agent.agent_class in item.allowed_classes


def equip_item(agent: AgentState, item: Item) -> None:
    if not can_equip(agent, item):
        return
    if item.slot == "weapon" and item.atk > agent.weapon.atk:
        agent.weapon = item
    elif item.slot == "armor" and item.pdef > agent.armor.pdef:
        agent.armor = item
    elif item.slot == "ring" and item.mdmg > agent.ring.mdmg:
        agent.ring = item


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
            events.append(
                GameEvent(tick, agent.name, f"move {cmd}", result, new_room_id)
            )
        else:
            events.append(
                GameEvent(
                    tick,
                    agent.name,
                    f"move {cmd}",
                    f"No exit to the {DIRECTION_NAMES.get(cmd, cmd)}.",
                    agent.room_id,
                )
            )

    elif cmd in ABILITY_REGISTRY:
        events.extend(resolve_ability(agent, cmd, arg, room, tick, agents, rooms))

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
            if npc.interactions_left > 0:
                npc.interactions_left -= 1
                dialogue = narrate_npc_dialogue(
                    npc.name, npc.title, npc.dialogue, agent.name
                )
                result = f"{npc.name} says: {dialogue}"
                summary = summarize_npc_dialogue(npc.name, dialogue)
                witness = f"{npc.name} says: {summary}"
                if npc.item and not npc.item_given:
                    agent.inventory.append(npc.item)
                    equip_item(agent, npc.item)
                    result += f"\n  {npc.name} gives {agent.name} a {npc.item.name}!"
                    witness += (
                        f" {npc.name} gives {agent.name} a {npc.item.name}."
                    )
                    npc.item_given = True
            else:
                result = f"{npc.name} has nothing more to say."
                witness = ""
            events.append(
                GameEvent(
                    tick,
                    agent.name,
                    f"tell {npc.name}",
                    result,
                    agent.room_id,
                    witness_text=witness,
                    category="lore",
                )
            )
        else:
            target_agent = None
            for a in agents:
                if (
                    a.alive
                    and a.room_id == agent.room_id
                    and a.name != agent.name
                    and target_name in a.name.lower()
                ):
                    target_agent = a
                    break
            if target_agent:
                result = f'{agent.name} tells {target_agent.name}: "{message}"'
                events.append(
                    GameEvent(
                        tick,
                        agent.name,
                        f"tell {target_agent.name}",
                        result,
                        agent.room_id,
                        category="comm",
                    )
                )
            else:
                others = agents_in_room(agents, agent.room_id, agent.name)
                npcs_here = [n.name for n in room.npcs]
                available = others + npcs_here
                if available:
                    result = f"No one named '{target_name}' here. You can talk to: {', '.join(available)}."
                else:
                    result = f"No one named '{target_name}' here. There is nobody to talk to in this room."
                events.append(
                    GameEvent(
                        tick,
                        agent.name,
                        f"tell {target_name}",
                        result,
                        agent.room_id,
                    )
                )

    elif cmd == "say":
        others = agents_in_room(agents, agent.room_id, agent.name)
        if others:
            result = f'{agent.name} says: "{arg}" (heard by {", ".join(others)})'
        else:
            result = f'{agent.name} says: "{arg}" (nobody else is here)'
        events.append(
            GameEvent(tick, agent.name, "say", result, agent.room_id, category="comm")
        )

    elif cmd == "whisper":
        parts = arg.split(None, 1)
        target_name = parts[0].lower() if parts else ""
        message = parts[1] if len(parts) > 1 else ""
        target_agent = None
        for a in agents:
            if (
                a.alive
                and a.room_id == agent.room_id
                and a.name != agent.name
                and target_name in a.name.lower()
            ):
                target_agent = a
                break
        if target_agent:
            result = f'{agent.name} whispers to {target_agent.name}: "{message}"'
            events.append(
                GameEvent(
                    tick,
                    agent.name,
                    f"whisper {target_agent.name}",
                    result,
                    agent.room_id,
                    category="comm",
                )
            )
        else:
            others = agents_in_room(agents, agent.room_id, agent.name)
            if others:
                result = f"No ally named '{target_name}' here. Allies in room: {', '.join(others)}."
            else:
                result = f"No ally named '{target_name}' here. You are alone."
            events.append(
                GameEvent(
                    tick,
                    agent.name,
                    f"whisper {target_name}",
                    result,
                    agent.room_id,
                )
            )

    elif cmd == "yell":
        result = f'{agent.name} yells: "{arg}"'
        events.append(
            GameEvent(tick, agent.name, "yell", result, agent.room_id, category="comm")
        )

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
            events.append(
                GameEvent(tick, agent.name, f"get {item.name}", result, agent.room_id)
            )
        else:
            available = [i.name for i in room.items]
            if available:
                result = f"No item named '{arg}' here. Items available: {', '.join(available)}."
            else:
                result = f"No item named '{arg}' here. There are no items to pick up in this room."
            events.append(
                GameEvent(tick, agent.name, f"get {arg}", result, agent.room_id)
            )

    else:
        events.append(
            GameEvent(
                tick, agent.name, cmd, f"Unknown command: {cmd}", agent.room_id
            )
        )

    return events


def check_boss_defeated(rooms: dict[str, Room]) -> bool:
    for room in rooms.values():
        for mob in room.mobs:
            if mob.is_boss and mob.hp <= 0:
                return True
    return False


def all_agents_dead(agents: list[AgentState]) -> bool:
    return all(not a.alive for a in agents)


# ── Witness helpers ──────────────────────────────────────────────────────


def witness(
    agents: list[AgentState],
    event_text: str,
    room_id: str,
    acting_agent_name: str = "",
    history: str = "action",
    skip_sender: bool = False,
) -> None:
    """Append an event to the appropriate history of all agents in the given room."""
    for a in agents:
        if a.alive and a.room_id == room_id:
            if skip_sender and a.name == acting_agent_name:
                continue
            text = f">> {event_text}" if a.name == acting_agent_name else event_text
            if history == "comm":
                a.comm_history.append(text)
                a.comm_history = a.comm_history[-COMM_HISTORY_SIZE:]
            elif history == "lore":
                a.lore_history.append(text)
                a.lore_history = a.lore_history[-LORE_HISTORY_SIZE:]
            else:
                a.action_history.append(text)
                a.action_history = a.action_history[-ACTION_HISTORY_SIZE:]


def witness_private(
    agents: list[AgentState],
    event_text: str,
    acting_agent_name: str,
    target_agent_name: str,
) -> None:
    """Only sender (with >>) and target see the event. Always comm history."""
    for a in agents:
        if a.name == acting_agent_name:
            a.comm_history.append(f">> {event_text}")
            a.comm_history = a.comm_history[-COMM_HISTORY_SIZE:]
        elif a.name == target_agent_name and a.alive:
            a.comm_history.append(event_text)
            a.comm_history = a.comm_history[-COMM_HISTORY_SIZE:]


def witness_yell(
    agents: list[AgentState],
    rooms: dict[str, Room],
    agent_name: str,
    message: str,
    source_room_id: str,
) -> None:
    """BFS broadcast with distance-dependent text formatting. Always comm history."""
    reachable = rooms_within_range(source_room_id, rooms, max_hops=3)
    source_room = rooms[source_room_id]
    for room_id, (dist, from_dir) in reachable.items():
        if dist == 0:
            text = f'{agent_name} yells: "{message}"'
        elif dist == 1:
            text = f'{agent_name} yells from the {from_dir} ({source_room.name}): "{message}"'
        else:
            text = f'{agent_name} yells in the distance: "{message}"'
        for a in agents:
            if a.alive and a.room_id == room_id:
                if a.name == agent_name:
                    continue
                a.comm_history.append(text)
                a.comm_history = a.comm_history[-COMM_HISTORY_SIZE:]


def witness_events(
    agents: list[AgentState],
    rooms: dict[str, Room],
    events: list[GameEvent],
    agent: AgentState,
    cmd: str,
    arg: str,
    action_str: str,
    pre_action_room: str,
) -> None:
    """Route events to agent histories based on type (move, whisper, yell, etc.)."""
    for e in events:
        result_line = e.witness_text or e.result.split("\n")[0]
        if e.action.startswith("move"):
            # Old room: others see departure
            witness(
                agents,
                f"{agent.name} leaves heading {DIRECTION_NAMES.get(cmd, cmd)}",
                pre_action_room,
            )
            # New room: others see arrival from the opposite direction
            arrival_dir = OPPOSITE_DIRECTION.get(cmd, "somewhere")
            for a in agents:
                if (
                    a.alive
                    and a.room_id == agent.room_id
                    and a.name != agent.name
                ):
                    a.action_history.append(
                        f"{agent.name} arrives from the {arrival_dir}"
                    )
                    a.action_history = a.action_history[-ACTION_HISTORY_SIZE:]
            # Moving agent: own action
            agent.action_history.append(f">> {action_str} → {result_line}")
            agent.action_history = agent.action_history[-ACTION_HISTORY_SIZE:]
        elif e.action.startswith("whisper"):
            target_name = e.action.split(None, 1)[1] if " " in e.action else ""
            witness_private(agents, result_line, agent.name, target_name)
        elif e.action == "yell":
            witness_yell(agents, rooms, agent.name, arg, pre_action_room)
        elif e.action == "say":
            witness(
                agents,
                result_line,
                agent.room_id,
                agent.name,
                history="comm",
                skip_sender=True,
            )
        else:
            witness(
                agents,
                result_line,
                agent.room_id,
                agent.name,
                history=e.category,
            )
