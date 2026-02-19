from __future__ import annotations

import logging

import config
from config import ACTION_HISTORY_SIZE, BASE_PERSONALITY, COMM_HISTORY_SIZE, LORE_HISTORY_SIZE, SPELL_COSTS
from llm import chat
from models import AgentState, Room

log = logging.getLogger("nachomud")

def _build_commands_help(agent: AgentState, room: Room) -> str:
    """Build dynamic commands list showing only what's currently possible."""
    lines = ["Available actions:"]

    # Movement — only show exits that exist
    dir_names = {"n": "north", "s": "south", "e": "east", "w": "west"}
    for d in ("n", "s", "e", "w"):
        if d in room.exits:
            lines.append(f"  {d} — Move {dir_names[d]}")

    # Combat — only show if enemies present
    living_mobs = [m for m in room.mobs if m.hp > 0]
    if living_mobs:
        lines.append("  attack <enemy> — Melee attack (weapon ATK)")
        if agent.mp >= SPELL_COSTS["missile"]:
            lines.append("  missile <enemy> — Magic missile (1 MP, ring MDMG)")
        if agent.mp >= SPELL_COSTS["fireball"]:
            lines.append("  fireball — AoE all enemies (3 MP, ring MDMG x2)")
        if agent.mp >= SPELL_COSTS["poison"]:
            lines.append("  poison <enemy> — Poison: 1 dmg/tick, 3 ticks (2 MP)")

    # Healing — only show if affordable
    if agent.mp >= SPELL_COSTS["heal"]:
        lines.append("  heal [ally] — Restore 30% max HP (2 MP)")

    # Items — only show if items on ground
    if room.items:
        lines.append("  get <item> — Pick up item (auto-equips if better)")

    # NPC interaction — only show if NPCs with dialogue remain
    if any(n.interactions_left > 0 for n in room.npcs):
        lines.append("  tell <NPC> <message> — Talk to an NPC")

    return "\n".join(lines)


def build_comm_prompt(agent: AgentState, sensory: str, allies_here: list[str]) -> str:
    """Build the communication phase prompt (before action phase)."""
    history_block = ""
    if agent.action_history:
        recent = agent.action_history[-ACTION_HISTORY_SIZE:]
        history_block += "\n=== RECENT EVENTS ===\n" + "\n".join(f"- {h}" for h in recent)
    if agent.comm_history:
        recent_comm = agent.comm_history[-COMM_HISTORY_SIZE:]
        history_block += "\n=== ALLY COMMUNICATIONS ===\n" + "\n".join(f"- {h}" for h in recent_comm)
    if agent.lore_history:
        recent_lore = agent.lore_history[-LORE_HISTORY_SIZE:]
        history_block += "\n=== NPC LORE ===\n" + "\n".join(f"- {h}" for h in recent_lore)

    comm_options = []
    if allies_here:
        for ally in allies_here:
            comm_options.append(f"tell {ally} <message>")
            comm_options.append(f"whisper {ally} <message>")
        comm_options.append("say <message>")
    comm_options.append("yell <message> — broadcast to nearby rooms, no target needed")
    comm_options.append("none — stay silent")
    options_block = "\n".join(f"  {o}" for o in comm_options)

    prompt = f"""You are {agent.name} the {agent.agent_class}.
{BASE_PERSONALITY} {agent.personality}

HP: {agent.hp}/{agent.max_hp} | MP: {agent.mp}/{agent.max_mp}

=== WHAT YOU SEE ===
{sensory}
{history_block}

Before acting, you may communicate with allies. Say "none" if nothing important.
Commands:
{options_block}

Think: <what's worth communicating?>
Comm: <command or "none">"""

    return prompt


def get_agent_comm(
    agent: AgentState, sensory: str, allies_here: list[str],
    room: Room | None = None, allies: list[AgentState] | None = None,
) -> tuple[str, str | None]:
    """Get optional communication from agent. Returns (think, comm_action_or_None)."""
    prompt = build_comm_prompt(agent, sensory, allies_here)
    system = f"You are {agent.name} the {agent.agent_class}. Decide if you need to communicate with allies before acting. Say 'none' if nothing important to share."

    raw = chat(system=system, message=prompt, model=config.AGENT_MODEL, max_tokens=150)
    think, comm = _parse_think_comm(raw)

    if comm is None:
        return think, None

    # Validate: only ally communication commands allowed
    if room is not None and allies is not None:
        cmd, arg = parse_action(comm)
        if not _is_valid_comm(cmd, arg, agent, room, allies):
            log.info("Comm invalid for %s: '%s' — skipping", agent.name, comm)
            return think, None

    return think, comm


def _parse_think_comm(raw: str) -> tuple[str, str | None]:
    """Extract think and comm from LLM response.

    Handles multi-line think content: everything between Think: and Comm:
    is captured as the think string.
    """
    think_lines: list[str] = []
    comm = None
    in_think = False
    for line in raw.strip().split("\n"):
        stripped = line.strip()
        if stripped.lower().startswith("think:"):
            in_think = True
            rest = stripped[6:].strip()
            if rest:
                think_lines.append(rest)
        elif stripped.lower().startswith("comm:"):
            in_think = False
            comm = stripped[5:].strip()
        elif in_think and stripped:
            think_lines.append(stripped)

    think = " ".join(think_lines)

    # Fallback: if no Comm: found, take the last non-empty line
    if comm is None:
        for line in reversed(raw.strip().split("\n")):
            line = line.strip()
            if line and not line.lower().startswith("think:"):
                comm = line
                break

    # Normalize "none" variants
    if comm and comm.lower().strip().rstrip(".!") in ("none", "silent", "nothing", "pass", "stay silent", "no"):
        comm = None

    return think, comm


def _is_valid_comm(cmd: str, arg: str, agent: AgentState, room: Room, allies: list[AgentState]) -> bool:
    """Check if a comm action is valid (ally-only communication)."""
    if cmd == "say":
        return bool(arg)
    if cmd == "yell":
        return bool(arg)
    if cmd in ("tell", "talk"):
        target = arg.split(None, 1)[0].lower() if arg else ""
        if not target:
            return False
        return any(a.alive and a.room_id == agent.room_id and a.name != agent.name and target in a.name.lower() for a in allies)
    if cmd == "whisper":
        target = arg.split(None, 1)[0].lower() if arg else ""
        if not target:
            return False
        return any(a.alive and a.room_id == agent.room_id and a.name != agent.name and target in a.name.lower() for a in allies)
    return False


def build_action_prompt(agent: AgentState, sensory: str, room: Room | None = None) -> str:
    history_block = ""
    if agent.action_history:
        recent = agent.action_history[-ACTION_HISTORY_SIZE:]
        history_block += "\n=== RECENT EVENTS ===\n" + "\n".join(f"- {h}" for h in recent)
    if agent.comm_history:
        recent_comm = agent.comm_history[-COMM_HISTORY_SIZE:]
        history_block += "\n=== ALLY COMMUNICATIONS ===\n" + "\n".join(f"- {h}" for h in recent_comm)
    if agent.lore_history:
        recent_lore = agent.lore_history[-LORE_HISTORY_SIZE:]
        history_block += "\n=== NPC LORE ===\n" + "\n".join(f"- {h}" for h in recent_lore)

    # Dynamic commands based on current state
    commands_help = _build_commands_help(agent, room) if room else ""

    prompt = f"""You are {agent.name} the {agent.agent_class}.
{BASE_PERSONALITY} {agent.personality}

Your quest: {config.QUEST_DESCRIPTION}

=== YOUR EQUIPMENT ===
Weapon: {agent.weapon.name} (ATK:{agent.weapon.atk}) | Armor: {agent.armor.name} (PDEF:{agent.armor.pdef}) | Ring: {agent.ring.name} (MDMG:{agent.ring.mdmg})
HP: {agent.hp}/{agent.max_hp} | MP: {agent.mp}/{agent.max_mp}
{history_block}

=== WHAT YOU SEE ===
{sensory}

{commands_help}

Think: <your reasoning>
Do: <your command>"""

    return prompt


MAX_RETRIES = 2


def build_valid_actions(agent: AgentState, room: Room, allies: list[AgentState]) -> list[str]:
    """Build a list of valid actions for the current game state."""
    actions = []

    # Movement
    dir_names = {"n": "north", "s": "south", "e": "east", "w": "west"}
    for d, target_id in room.exits.items():
        actions.append(f"{d} - Move {dir_names.get(d, d)}")

    # Combat (only if enemies present)
    living_mobs = [m for m in room.mobs if m.hp > 0]
    for mob in living_mobs:
        actions.append(f"attack {mob.name}")
        if agent.mp >= SPELL_COSTS["missile"]:
            actions.append(f"missile {mob.name} ({SPELL_COSTS['missile']} MP)")
        if agent.mp >= SPELL_COSTS["poison"]:
            actions.append(f"poison {mob.name} ({SPELL_COSTS['poison']} MP)")
    if living_mobs and agent.mp >= SPELL_COSTS["fireball"]:
        actions.append(f"fireball - Hit all enemies ({SPELL_COSTS['fireball']} MP)")

    # Healing
    if agent.mp >= SPELL_COSTS["heal"]:
        actions.append(f"heal - Heal yourself ({SPELL_COSTS['heal']} MP)")
        for a in allies:
            if a.alive and a.room_id == agent.room_id and a.name != agent.name:
                actions.append(f"heal {a.name} ({SPELL_COSTS['heal']} MP)")

    # Items
    for item in room.items:
        actions.append(f"get {item.name}")

    # NPCs
    for npc in room.npcs:
        if npc.interactions_left > 0:
            actions.append(f"tell {npc.name} <message>")

    return actions


def build_retry_prompt(agent: AgentState, invalid_action: str, valid_actions: list[str]) -> str:
    actions_list = "\n".join(f"  - {a}" for a in valid_actions)
    return f"""Your action "{invalid_action}" was invalid. Here are your available actions:

{actions_list}

Evaluate each option for your current situation, then choose the best one.
Think: <evaluate your options>
Do: <your command>"""


def _parse_think_do(raw: str) -> tuple[str, str]:
    """Extract think and action from LLM response.

    Handles multi-line think content: everything between Think: and Do:
    is captured as the think string.
    """
    think_lines: list[str] = []
    action = ""
    in_think = False
    for line in raw.strip().split("\n"):
        stripped = line.strip()
        if stripped.lower().startswith("think:"):
            in_think = True
            rest = stripped[6:].strip()
            if rest:
                think_lines.append(rest)
        elif stripped.lower().startswith("do:"):
            in_think = False
            action = stripped[3:].strip()
        elif in_think and stripped:
            think_lines.append(stripped)

    think = " ".join(think_lines)

    # Fallback: if no "Do:" found, take the last non-empty line
    if not action:
        for line in reversed(raw.strip().split("\n")):
            line = line.strip()
            if line and not line.lower().startswith("think:"):
                action = line
                break

    if action.startswith("/"):
        action = action[1:]
    return think, action


def _is_valid_action(cmd: str, arg: str, room: Room, agent: AgentState, allies: list[AgentState]) -> bool:
    """Check if a parsed action is valid for the current game state."""
    if cmd in ("n", "s", "e", "w"):
        return cmd in room.exits

    if cmd == "attack":
        return any(m.hp > 0 and arg.lower() in m.name.lower() for m in room.mobs) if arg else False

    if cmd == "missile":
        if agent.mp < SPELL_COSTS["missile"]:
            return False
        return any(m.hp > 0 and arg.lower() in m.name.lower() for m in room.mobs) if arg else False

    if cmd == "fireball":
        return agent.mp >= SPELL_COSTS["fireball"] and any(m.hp > 0 for m in room.mobs)

    if cmd == "poison":
        if agent.mp < SPELL_COSTS["poison"]:
            return False
        return any(m.hp > 0 and arg.lower() in m.name.lower() for m in room.mobs) if arg else False

    if cmd == "heal":
        if agent.mp < SPELL_COSTS["heal"]:
            return False
        if not arg:
            return True  # heal self
        # Check if targeting self or a valid ally
        if arg.lower() in agent.name.lower():
            return True
        return any(a.alive and a.room_id == agent.room_id and arg.lower() in a.name.lower() for a in allies)

    if cmd in ("get", "take", "pick"):
        return any(arg.lower() in i.name.lower() for i in room.items) if arg else False

    if cmd in ("tell", "talk"):
        target = arg.split(None, 1)[0].lower() if arg else ""
        if not target:
            return False
        # Check NPCs
        if any(target in n.name.lower() for n in room.npcs):
            return True
        # Check allies in room
        return any(a.alive and a.room_id == agent.room_id and a.name != agent.name and target in a.name.lower() for a in allies)

    if cmd == "say":
        return bool(arg)

    if cmd == "whisper":
        target = arg.split(None, 1)[0].lower() if arg else ""
        if not target:
            return False
        return any(a.alive and a.room_id == agent.room_id and a.name != agent.name and target in a.name.lower() for a in allies)

    if cmd == "yell":
        return bool(arg)

    return False


def get_agent_action(
    agent: AgentState, sensory: str,
    room: Room | None = None, allies: list[AgentState] | None = None,
) -> tuple[str, str, list[str]]:
    """Returns (think, action, retries) tuple. retries is a list of invalid action strings that were rejected."""
    prompt = build_action_prompt(agent, sensory, room=room)
    system = f"You are {agent.name} the {agent.agent_class} in a dungeon crawler. Think briefly about your situation, then output your command after 'Do:'."

    raw = chat(system=system, message=prompt, model=config.AGENT_MODEL, max_tokens=150)
    think, action = _parse_think_do(raw)
    retries: list[str] = []

    # If we have room context, validate and retry on failure
    if room is not None and allies is not None and action:
        cmd, arg = parse_action(action)
        for attempt in range(MAX_RETRIES):
            if _is_valid_action(cmd, arg, room, agent, allies):
                break
            # Invalid — retry with valid actions list
            valid_actions = build_valid_actions(agent, room, allies)
            if not valid_actions:
                break  # nothing valid to do (shouldn't happen)
            retries.append(action)
            log.info("Retry %d/%d for %s: '%s' invalid. Valid: %s", attempt + 1, MAX_RETRIES, agent.name, action, valid_actions)
            retry_prompt = build_retry_prompt(agent, action, valid_actions)
            raw = chat(system=system, message=retry_prompt, model=config.AGENT_MODEL, max_tokens=200)
            think, action = _parse_think_do(raw)
            cmd, arg = parse_action(action)

    return think, action, retries


_DIRECTION_ALIASES = {
    "north": "n", "south": "s", "east": "e", "west": "w",
}

def parse_action(action: str) -> tuple[str, str]:
    """Returns (command, argument). Argument may be empty."""
    parts = action.strip().split(None, 1)
    if not parts:
        return ("say", "I'm not sure what to do.")
    cmd = parts[0].lower()
    arg = parts[1] if len(parts) > 1 else ""

    # Handle "move north", "go north", "walk east", etc.
    if cmd in ("move", "go", "walk", "run") and arg:
        direction = arg.strip().lower()
        direction = _DIRECTION_ALIASES.get(direction, direction)
        if direction in ("n", "s", "e", "w"):
            return (direction, "")

    # Handle bare direction words: "north", "south", "east", "west"
    resolved = _DIRECTION_ALIASES.get(cmd)
    if resolved:
        return (resolved, "")

    return (cmd, arg)
