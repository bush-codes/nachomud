from __future__ import annotations

import logging

import config
from config import ABILITY_DEFINITIONS, ACTION_HISTORY_SIZE, BASE_PERSONALITY, CLASS_DEFINITIONS, COMM_HISTORY_SIZE, LORE_HISTORY_SIZE, SPELL_COSTS
from llm import chat
from models import AgentState, Room

log = logging.getLogger("nachomud")


def _build_party_roster(agent: AgentState, allies: list[AgentState]) -> str:
    """Build a party roster showing all allies with class, HP, and location."""
    lines = ["=== YOUR PARTY ==="]
    for a in allies:
        if a.name == agent.name:
            continue
        resource = f"AP:{a.ap}/{a.max_ap}" if a.agent_class == "Warrior" else f"MP:{a.mp}/{a.max_mp}"
        here = "here" if a.alive and a.room_id == agent.room_id else "not here"
        status = f"HP:{a.hp}/{a.max_hp} {resource} [{here}]" if a.alive else "FALLEN"
        lines.append(f"  {a.name} the {a.agent_class} — {status}")
    return "\n".join(lines)


def build_comm_prompt(agent: AgentState, sensory: str, allies_here: list[str], allies: list[AgentState] | None = None) -> str:
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

    party_block = _build_party_roster(agent, allies) if allies else ""

    prompt = f"""You are {agent.name} the {agent.agent_class}.
{BASE_PERSONALITY} {agent.personality}

HP: {agent.hp}/{agent.max_hp} | {"AP: " + str(agent.ap) + "/" + str(agent.max_ap) if agent.max_ap > 0 else "MP: " + str(agent.mp) + "/" + str(agent.max_mp)}

{party_block}

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
    prompt = build_comm_prompt(agent, sensory, allies_here, allies=allies)
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


def build_action_prompt(agent: AgentState, sensory: str, room: Room | None = None, allies: list[AgentState] | None = None) -> str:
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
    if room and allies is not None:
        valid = build_valid_actions(agent, room, allies)
        commands_help = "Available actions:\n" + "\n".join(f"  {a}" for a in valid)
    else:
        commands_help = ""
    party_block = _build_party_roster(agent, allies) if allies else ""

    prompt = f"""You are {agent.name} the {agent.agent_class}.
{BASE_PERSONALITY} {agent.personality}

Your quest: {config.QUEST_DESCRIPTION}

=== YOUR EQUIPMENT ===
Weapon: {agent.weapon.name} (ATK:{agent.weapon.atk}) | Armor: {agent.armor.name} (PDEF:{agent.armor.pdef}) | Ring: {agent.ring.name} (MDMG:{agent.ring.mdmg})
HP: {agent.hp}/{agent.max_hp} | {"AP: " + str(agent.ap) + "/" + str(agent.max_ap) if agent.max_ap > 0 else "MP: " + str(agent.mp) + "/" + str(agent.max_mp)}

{party_block}
{history_block}

=== WHAT YOU SEE ===
{sensory}

{commands_help}

Think: <your reasoning>
Do: <your command>"""

    return prompt


MAX_RETRIES = 2


def build_valid_actions(agent: AgentState, room: Room, allies: list[AgentState]) -> list[str]:
    """Build a list of valid actions for the current game state (class-aware).

    Each entry includes the concrete command, specific targets, cost, and description.
    """
    actions = []

    # Movement
    dir_names = {"n": "north", "s": "south", "e": "east", "w": "west"}
    for d, target_id in room.exits.items():
        actions.append(f"{d} — Move {dir_names.get(d, d)}")

    # Class abilities
    living_mobs = [m for m in room.mobs if m.hp > 0]
    class_def = CLASS_DEFINITIONS.get(agent.agent_class)
    ability_list = class_def["abilities"] if class_def else ["attack"]

    for ability_name in ability_list:
        defn = ABILITY_DEFINITIONS.get(ability_name)
        if not defn:
            continue

        cost = defn["cost"]
        cost_type = defn["cost_type"]
        if cost_type == "mp" and agent.mp < cost:
            continue
        if cost_type == "ap" and agent.ap < cost:
            continue
        if cost_type == "hp" and agent.hp <= cost:
            continue

        target = defn["target"]
        cmd_display = ability_name.replace("_", " ")
        cost_str = f"({cost} {cost_type.upper()})" if cost_type != "free" else ""
        desc = defn["description"]

        if target == "enemy":
            for mob in living_mobs:
                actions.append(f"{cmd_display} {mob.name} — {desc} {cost_str}".strip())
        elif target == "all_enemies":
            if living_mobs:
                actions.append(f"{cmd_display} — {desc} {cost_str}".strip())
        elif target == "ally":
            for a in allies:
                if a.alive and a.room_id == agent.room_id and a.name != agent.name:
                    actions.append(f"{cmd_display} {a.name} — {desc} {cost_str}".strip())
        elif target == "ally_or_self":
            actions.append(f"{cmd_display} — {desc} (self) {cost_str}".strip())
            for a in allies:
                if a.alive and a.room_id == agent.room_id and a.name != agent.name:
                    actions.append(f"{cmd_display} {a.name} — {desc} {cost_str}".strip())
        elif target == "self":
            actions.append(f"{cmd_display} — {desc} {cost_str}".strip())

    # Items
    for item in room.items:
        actions.append(f"get {item.name} — Pick up item (auto-equips if better)")

    # NPCs
    for npc in room.npcs:
        if npc.interactions_left > 0:
            actions.append(f"tell {npc.name} <message> — Talk to NPC")

    return actions


def build_retry_prompt(original_prompt: str, invalid_action: str, valid_actions: list[str]) -> str:
    actions_list = "\n".join(f"  - {a}" for a in valid_actions)

    # Strip the trailing Think:/Do: lines from the original prompt
    lines = original_prompt.rstrip().split("\n")
    while lines and lines[-1].strip().startswith(("Think:", "Do:")):
        lines.pop()
    base = "\n".join(lines).rstrip()

    return f"""Your action "{invalid_action}" was invalid. You MUST choose from these actions:

{actions_list}

{base}

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
    """Check if a parsed action is valid for the current game state (class-aware)."""
    if cmd in ("n", "s", "e", "w"):
        return cmd in room.exits

    # Check if cmd is a class ability
    class_def = CLASS_DEFINITIONS.get(agent.agent_class)
    ability_list = class_def["abilities"] if class_def else ["attack"]

    if cmd in ABILITY_DEFINITIONS:
        if cmd not in ability_list:
            return False  # not this class's ability

        defn = ABILITY_DEFINITIONS[cmd]
        cost = defn["cost"]
        cost_type = defn["cost_type"]
        if cost_type == "mp" and agent.mp < cost:
            return False
        if cost_type == "ap" and agent.ap < cost:
            return False
        if cost_type == "hp" and agent.hp <= cost:
            return False

        target = defn["target"]
        living_mobs = [m for m in room.mobs if m.hp > 0]

        if target == "enemy":
            return any(arg.lower() in m.name.lower() for m in living_mobs) if arg else False
        if target == "all_enemies":
            return bool(living_mobs)
        if target == "self":
            return True
        if target == "ally_or_self":
            if not arg:
                return True  # self
            if arg.lower() in agent.name.lower():
                return True
            return any(a.alive and a.room_id == agent.room_id and arg.lower() in a.name.lower() for a in allies)
        if target == "ally":
            if not arg:
                return False
            return any(a.alive and a.room_id == agent.room_id and a.name != agent.name and arg.lower() in a.name.lower() for a in allies)
        if target == "all_allies":
            return True
        return False

    if cmd in ("get", "take", "pick"):
        return any(arg.lower() in i.name.lower() for i in room.items) if arg else False

    if cmd in ("tell", "talk"):
        target = arg.split(None, 1)[0].lower() if arg else ""
        if not target:
            return False
        if any(target in n.name.lower() for n in room.npcs):
            return True
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
    prompt = build_action_prompt(agent, sensory, room=room, allies=allies)
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
            retry_prompt = build_retry_prompt(prompt, action, valid_actions)
            raw = chat(system=system, message=retry_prompt, model=config.AGENT_MODEL, max_tokens=200)
            think, action = _parse_think_do(raw)
            cmd, arg = parse_action(action)

    return think, action, retries


_DIRECTION_ALIASES = {
    "north": "n", "south": "s", "east": "e", "west": "w",
}

# Multi-word abilities: map "lay on hands" → "lay_on_hands", etc.
_MULTI_WORD_ABILITIES = {
    "lay on hands": "lay_on_hands",
    "aimed shot": "aimed_shot",
    "poison arrow": "poison_arrow",
    "arcane storm": "arcane_storm",
    "holy bolt": "holy_bolt",
    "smoke bomb": "smoke_bomb",
}

def parse_action(action: str) -> tuple[str, str]:
    """Returns (command, argument). Argument may be empty."""
    stripped = action.strip()
    if not stripped:
        return ("say", "I'm not sure what to do.")

    # Check for multi-word abilities first
    lower = stripped.lower()
    for phrase, ability_name in _MULTI_WORD_ABILITIES.items():
        if lower.startswith(phrase):
            rest = stripped[len(phrase):].strip()
            return (ability_name, rest)

    # Also handle underscore forms directly (lay_on_hands, etc.)
    parts = stripped.split(None, 1)
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
