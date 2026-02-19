from __future__ import annotations

import logging

from config import ACTION_HISTORY_SIZE, AGENT_MODEL, BASE_PERSONALITY, SPELL_COSTS
from llm import chat
from models import AgentState, Room

log = logging.getLogger("nachomud")

COMMANDS_HELP = """Commands:
  n / s / e / w         - Move in a direction
  attack <enemy>        - Melee attack an enemy (weapon ATK)
  missile <enemy>       - Magic missile an enemy (1 MP, ring MDMG)
  fireball              - AoE all enemies in room (3 MP, ring MDMG x2)
  poison <enemy>        - Poison an enemy: 1 dmg/tick, 3 ticks (2 MP)
  heal [ally]           - Restore 30% max HP (2 MP, heals self if no target)
  get <item>            - Pick up item (auto-equips if better)
  tell <name> <msg>     - Speak to a specific NPC or ally

Target rules:
  Enemies → attack, missile, fireball, poison
  Allies (party members) → heal, tell
  NPCs → tell only (cannot attack or heal NPCs)
  Items → get only"""


def build_discussion_prompt(agent: AgentState, sensory: str, allies: list[str], discussion_so_far: list[str]) -> str:
    last_action_line = ""
    if agent.last_action:
        last_action_line = f"\nYour last action: {agent.last_action}"
        if agent.last_result:
            last_action_line += f"\nResult: {agent.last_result}"

    discussion_block = ""
    if discussion_so_far:
        discussion_block = "\n=== DISCUSSION THIS TURN ===\n" + "\n".join(discussion_so_far)

    prompt = f"""You are {agent.name} the {agent.agent_class}.
{BASE_PERSONALITY} {agent.personality}

Your quest: navigate the Durnhollow fortress with your allies, reach the Shadowfell Rift, and close it by defeating the final boss.

HP: {agent.hp}/{agent.max_hp} | MP: {agent.mp}/{agent.max_mp}
{last_action_line}

=== WHAT YOU SEE ===
{sensory}
{discussion_block}

{COMMANDS_HELP}

{"You are alone here. Think out loud about your situation and what you should do. Being separated from allies is dangerous." if not allies else "You are discussing strategy with your allies before acting."} Consider enemies to fight, items to pick up, NPCs to talk to, and exits to explore. Picking up items automatically equips them if they are better than your current gear. What should {"you" if not allies else "the group"} do next? Speak in character in 1-2 short sentences."""

    return prompt


def get_agent_discussion(agent: AgentState, sensory: str, allies: list[str], discussion_so_far: list[str]) -> str:
    prompt = build_discussion_prompt(agent, sensory, allies, discussion_so_far)

    raw = chat(
        system=f"You are {agent.name} the {agent.agent_class}. Speak in character in 1-2 sentences about what the group should do next. Consider everything you see: enemies to fight, items on the ground to pick up, NPCs to talk to, and exits to explore.",
        message=prompt,
        model=AGENT_MODEL,
        max_tokens=100,
    )
    utterance = raw.strip().split("\n")[0].strip()
    return utterance


def build_action_prompt(agent: AgentState, sensory: str, round0_plan: list[str] | None = None) -> str:
    history_block = ""
    if agent.action_history:
        recent = agent.action_history[-ACTION_HISTORY_SIZE:]
        # Count consecutive failures from the end (only for this agent's own actions)
        fail_markers = ("No enemy", "already dead", "No enemies", "No living mob",
                        "No one named", "Not enough MP", "Unknown command",
                        "No item named", "No ally named", "No exit", "not an enemy",
                        "is an item", "is your ally", "is an NPC", "is an enemy")
        own_actions = [e for e in recent if e.startswith(">>")]
        streak = 0
        for entry in reversed(own_actions):
            if any(m in entry for m in fail_markers):
                streak += 1
            else:
                break
        streak_line = f"WARNING: Your last {streak} actions failed.\n" if streak >= 2 else ""
        history_block = "\n=== RECENT EVENTS (what you witnessed) ===\n" + streak_line + "\n".join(f"- {h}" for h in recent)

    plan_block = ""
    if round0_plan:
        plan_block = "\n=== PARTY PLAN (from before entering) ===\n" + "\n".join(f"- {p}" for p in round0_plan)

    # Build conditional warnings
    warnings = []
    if agent.hp >= agent.max_hp:
        warnings.append("You are at full HP — healing would be wasted.")
    unavailable = [f"{spell} ({cost} MP)" for spell, cost in SPELL_COSTS.items() if agent.mp < cost]
    if unavailable:
        warnings.append(f"Not enough MP for: {', '.join(unavailable)}.")
    warning_block = "\n".join(warnings)

    prompt = f"""You are {agent.name} the {agent.agent_class}.
{BASE_PERSONALITY} {agent.personality}

Your quest: navigate the Durnhollow fortress with your allies, reach the Shadowfell Rift, and close it by defeating the final boss.

=== YOUR EQUIPMENT ===
Weapon: {agent.weapon.name} (ATK:{agent.weapon.atk}) | Armor: {agent.armor.name} (PDEF:{agent.armor.pdef}) | Ring: {agent.ring.name} (MDMG:{agent.ring.mdmg})
HP: {agent.hp}/{agent.max_hp} | MP: {agent.mp}/{agent.max_mp}
{warning_block}
{plan_block}
{history_block}

=== WHAT YOU SEE ===
{sensory}

{COMMANDS_HELP}

You MUST take a real game action — move, attack, cast a spell, pick up an item, or talk to an NPC. You can ONLY target enemies, items, and NPCs in YOUR current room. To reach things in nearby rooms, move there first.

First think about your situation in 1 sentence, then give your command.
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

    # Ally communication
    for a in allies:
        if a.alive and a.room_id == agent.room_id and a.name != agent.name:
            actions.append(f"tell {a.name} <message>")

    return actions


def build_retry_prompt(agent: AgentState, invalid_action: str, valid_actions: list[str]) -> str:
    actions_list = "\n".join(f"  - {a}" for a in valid_actions)
    return f"""Your action "{invalid_action}" was invalid. Here are your available actions:

{actions_list}

Evaluate each option for your current situation, then choose the best one.
Think: <evaluate your options>
Do: <your command>"""


def _parse_think_do(raw: str) -> tuple[str, str]:
    """Extract think and action from LLM response."""
    think = ""
    action = ""
    for line in raw.strip().split("\n"):
        line = line.strip()
        if line.lower().startswith("think:"):
            think = line[6:].strip()
        elif line.lower().startswith("do:"):
            action = line[3:].strip()

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
        return True

    return False


def get_agent_action(
    agent: AgentState, sensory: str,
    room: Room | None = None, allies: list[AgentState] | None = None,
    round0_plan: list[str] | None = None,
) -> tuple[str, str, list[str]]:
    """Returns (think, action, retries) tuple. retries is a list of invalid action strings that were rejected."""
    prompt = build_action_prompt(agent, sensory, round0_plan=round0_plan)
    system = f"You are {agent.name} the {agent.agent_class} in a dungeon crawler. Think briefly about your situation, then output your command after 'Do:'."

    raw = chat(system=system, message=prompt, model=AGENT_MODEL, max_tokens=150)
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
            raw = chat(system=system, message=retry_prompt, model=AGENT_MODEL, max_tokens=200)
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
