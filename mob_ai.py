"""Mob AI — LLM-driven mob turns with prompt building and action parsing.

Mobs get a comm phase (bosses always talk, regular mobs occasionally) and an
action phase (choose from their ability list). Taunt and sleep enforcement
are applied after the LLM decision.
"""
from __future__ import annotations

import math
import logging
import random

import config
from config import ABILITY_DEFINITIONS
from effects import (
    apply_effect,
    has_effect,
    is_incapacitated,
    modify_incoming_damage,
    modify_source_damage,
)
from llm import chat
from models import AgentState, GameEvent, Mob, Room, StatusEffect

log = logging.getLogger("nachomud")


def _agents_in_mob_room(mob: Mob, agents: list[AgentState]) -> list[AgentState]:
    """Return living agents in the same room as the mob."""
    return [a for a in agents if a.alive and a.room_id == mob.room_id]


def _mob_affordable_abilities(mob: Mob) -> list[str]:
    """Return abilities the mob can currently afford."""
    affordable = []
    for ability_name in mob.abilities:
        defn = ABILITY_DEFINITIONS.get(ability_name)
        if not defn:
            continue
        # Mobs don't have MP/AP/HP cost restrictions for now — they just use abilities.
        # (Mob resource management could be added later if desired.)
        affordable.append(ability_name)
    return affordable


def build_mob_action_prompt(
    mob: Mob,
    room: Room,
    agents_here: list[AgentState],
) -> str:
    """Build the action prompt for a mob's LLM-driven turn."""
    # List agents as targets
    targets = []
    for a in agents_here:
        targets.append(f"  {a.name} the {a.agent_class} — HP:{a.hp}/{a.max_hp}")

    targets_block = "\n".join(targets) if targets else "  No enemies visible."

    # List available abilities
    ability_lines = []
    for ability_name in mob.abilities:
        defn = ABILITY_DEFINITIONS.get(ability_name)
        if not defn:
            continue
        target_type = defn["target"]
        cmd_display = ability_name.replace("_", " ")
        if target_type in ("enemy", "ally_or_self"):
            ability_lines.append(f"  {cmd_display} <target> — {defn['description']}")
        else:
            ability_lines.append(f"  {cmd_display} — {defn['description']}")

    abilities_block = "\n".join(ability_lines) if ability_lines else "  attack <target>"

    # Status info
    status_parts = [f"HP: {mob.hp}/{mob.max_hp}", f"ATK: {mob.atk}"]
    if mob.pdef:
        status_parts.append(f"PDEF: {mob.pdef}")
    if mob.mdef:
        status_parts.append(f"MDEF: {mob.mdef}")
    status_line = " | ".join(status_parts)

    prompt = f"""You are {mob.name}, a monster in a dungeon.
{mob.personality if mob.personality else "Hostile and aggressive."}

{status_line}
Location: {room.name}

=== ENEMIES (adventurers to fight) ===
{targets_block}

=== YOUR ABILITIES ===
{abilities_block}

Choose your action. Target the most dangerous or weakest adventurer as appropriate.
Think: <brief tactical reasoning>
Do: <your command>"""

    return prompt


def build_mob_comm_prompt(mob: Mob, room: Room, agents_here: list[AgentState]) -> str:
    """Build prompt for mob communication (taunts, threats, etc.)."""
    agent_names = ", ".join(a.name for a in agents_here) if agents_here else "no one"

    prompt = f"""You are {mob.name}, a monster in {room.name}.
{mob.personality if mob.personality else "Hostile and aggressive."}

Adventurers present: {agent_names}

Say something threatening, taunting, or atmospheric. Keep it to ONE short sentence (under 15 words).
If you have nothing to say, respond with "none".

Say:"""

    return prompt


def _parse_mob_action(raw: str) -> str:
    """Extract action from mob's LLM response. Simpler than agent parsing."""
    action = ""
    for line in raw.strip().split("\n"):
        stripped = line.strip()
        if stripped.lower().startswith("do:"):
            action = stripped[3:].strip()
            break

    # Fallback: last non-empty, non-think line
    if not action:
        for line in reversed(raw.strip().split("\n")):
            line = line.strip()
            if line and not line.lower().startswith("think:"):
                action = line
                break

    if action.startswith("/"):
        action = action[1:]
    return action


def _parse_mob_comm(raw: str) -> str | None:
    """Extract communication from mob's LLM response."""
    text = raw.strip()
    # Handle "Say:" prefix
    if text.lower().startswith("say:"):
        text = text[4:].strip()

    # Check for silence
    if text.lower().strip().rstrip(".!") in ("none", "silent", "nothing", "pass", ""):
        return None

    # Trim to first sentence if too long
    if len(text) > 100:
        text = text[:100].rsplit(" ", 1)[0] + "..."

    return text


def _parse_mob_command(action_str: str) -> tuple[str, str]:
    """Parse mob action string into (command, argument)."""
    stripped = action_str.strip()
    if not stripped:
        return ("attack", "")

    # Handle multi-word ability names for mobs too
    lower = stripped.lower()
    for phrase, ability_name in {
        "lay on hands": "lay_on_hands",
        "aimed shot": "aimed_shot",
        "poison arrow": "poison_arrow",
        "arcane storm": "arcane_storm",
        "holy bolt": "holy_bolt",
        "smoke bomb": "smoke_bomb",
    }.items():
        if lower.startswith(phrase):
            rest = stripped[len(phrase):].strip()
            return (ability_name, rest)

    parts = stripped.split(None, 1)
    cmd = parts[0].lower()
    arg = parts[1] if len(parts) > 1 else ""
    return (cmd, arg)


def _find_taunter(mob: Mob, agents: list[AgentState]) -> AgentState | None:
    """If mob is taunted, find the taunter (must be alive and in same room)."""
    for se in mob.status_effects:
        if se.name == "taunted":
            for a in agents:
                if a.alive and a.room_id == mob.room_id and a.name == se.source:
                    return a
    return None


def get_mob_action(
    mob: Mob,
    room: Room,
    agents: list[AgentState],
    rooms: dict[str, Room],
    tick: int,
) -> tuple[str, str]:
    """Get mob's action via LLM. Returns (ability_name, target_name).

    Enforces:
    - Sleep: skip turn entirely
    - Taunt: override target to be the taunter
    Fallback: attack random agent if LLM returns invalid
    """
    # Sleep enforcement
    if is_incapacitated(mob):
        return ("", "")  # skip turn

    agents_here = _agents_in_mob_room(mob, agents)
    if not agents_here:
        return ("", "")  # no targets, skip

    # Get LLM action
    prompt = build_mob_action_prompt(mob, room, agents_here)
    system = f"You are {mob.name}, a monster. Choose your action. Output format: Think: <reasoning>\\nDo: <command>"

    try:
        raw = chat(system=system, message=prompt, model=config.AGENT_MODEL, max_tokens=100)
        action_str = _parse_mob_action(raw)
    except Exception as e:
        log.error("Mob %s action failed: %s", mob.name, e)
        action_str = ""

    # Parse the action
    cmd, arg = _parse_mob_command(action_str)

    # Validate: must be an ability the mob has
    if cmd not in mob.abilities:
        # Fallback to attack
        cmd = "attack"

    # Taunt enforcement: override target
    taunter = _find_taunter(mob, agents)
    if taunter:
        defn = ABILITY_DEFINITIONS.get(cmd, {})
        target_type = defn.get("target", "enemy")
        if target_type == "enemy":
            arg = taunter.name

    # If targeting ability but no valid target specified, pick one
    defn = ABILITY_DEFINITIONS.get(cmd, {})
    target_type = defn.get("target", "enemy")
    if target_type == "enemy" and not arg:
        # Pick random agent in room
        arg = random.choice(agents_here).name
    elif target_type == "enemy" and arg:
        # Validate target exists
        arg_lower = arg.lower()
        found = any(arg_lower in a.name.lower() for a in agents_here)
        if not found:
            arg = random.choice(agents_here).name

    return (cmd, arg)


def get_mob_comm(
    mob: Mob,
    room: Room,
    agents: list[AgentState],
) -> str | None:
    """Get optional communication from mob. Bosses always comm, others 30% chance."""
    if is_incapacitated(mob):
        return None

    agents_here = _agents_in_mob_room(mob, agents)
    if not agents_here:
        return None

    # Bosses always talk, regular mobs 30% chance
    if not mob.is_boss and random.random() > 0.3:
        return None

    prompt = build_mob_comm_prompt(mob, room, agents_here)
    system = f"You are {mob.name}. Say something short and threatening, or 'none'."

    try:
        raw = chat(system=system, message=prompt, model=config.AGENT_MODEL, max_tokens=50)
        return _parse_mob_comm(raw)
    except Exception as e:
        log.error("Mob %s comm failed: %s", mob.name, e)
        return None


# ── Mob ability resolution ──────────────────────────────────────────────

def _find_agent_target(
    target_name: str, agents: list[AgentState], room_id: str,
) -> AgentState | None:
    """Find a living agent in the room by name substring match."""
    target_lower = target_name.lower()
    for a in agents:
        if a.alive and a.room_id == room_id and target_lower in a.name.lower():
            return a
    return None


def resolve_mob_ability(
    mob: Mob,
    ability_name: str,
    target_name: str,
    room: Room,
    tick: int,
    agents: list[AgentState],
) -> list[GameEvent]:
    """Resolve a mob's ability use against agents. Returns list of GameEvents.

    Mob abilities are simpler than agent abilities:
    - attack: mob.atk vs target.pdef (min 1)
    - Mob DoTs (curse, poison_arrow, bleed): apply StatusEffect to target
    - Mob AoE: damage all agents in room
    - Mob heals: heal self or ally mob
    - Sleep: apply sleep to agent
    """
    if is_incapacitated(mob):
        return [GameEvent(tick, mob.name, ability_name,
                         f"{mob.name} is asleep and cannot act!", room.id)]

    # Dispatch by ability type
    defn = ABILITY_DEFINITIONS.get(ability_name, {})
    target_type = defn.get("target", "enemy")

    # For mobs, "enemy" = agents, targets are flipped from the agent perspective
    if ability_name == "attack":
        return _resolve_mob_attack(mob, target_name, room, tick, agents)
    elif ability_name in ("curse", "poison_arrow", "bleed"):
        return _resolve_mob_dot(mob, ability_name, target_name, room, tick, agents)
    elif ability_name == "sleep":
        return _resolve_mob_sleep(mob, target_name, room, tick, agents)
    elif ability_name == "heal":
        return _resolve_mob_heal(mob, room, tick)
    elif target_type == "all_enemies":
        # AoE ability — hit all agents in room
        return _resolve_mob_aoe(mob, ability_name, room, tick, agents)
    elif target_type == "enemy":
        # Single-target damage ability
        return _resolve_mob_single_attack(mob, ability_name, target_name, room, tick, agents)
    else:
        # Fallback: treat as basic attack
        return _resolve_mob_attack(mob, target_name, room, tick, agents)


def _resolve_mob_attack(
    mob: Mob, target_name: str, room: Room, tick: int, agents: list[AgentState],
) -> list[GameEvent]:
    """Mob basic attack: mob.atk vs target pdef, min 1."""
    target = _find_agent_target(target_name, agents, room.id)
    if not target:
        return [GameEvent(tick, mob.name, "attack", f"{mob.name} attacks the air!", room.id)]

    raw_damage = mob.atk
    raw_damage = modify_source_damage(mob, raw_damage)
    pdef = target.armor.pdef + target.ring.pdef
    damage = max(1, raw_damage - pdef) if raw_damage > 0 else 0
    damage = modify_incoming_damage(target, damage)

    target.hp = max(0, target.hp - damage)
    result = f"{mob.name} attacks {target.name} for {damage} damage. ({target.name} HP: {target.hp}/{target.max_hp})"
    if target.hp <= 0:
        target.hp = 0
        target.alive = False
        result += f" {target.name} has fallen!"

    return [GameEvent(tick, mob.name, f"attack {target.name}", result, room.id)]


def _resolve_mob_single_attack(
    mob: Mob, ability_name: str, target_name: str, room: Room, tick: int,
    agents: list[AgentState],
) -> list[GameEvent]:
    """Mob single-target special ability: mob.atk * 1.5 vs pdef."""
    target = _find_agent_target(target_name, agents, room.id)
    if not target:
        return [GameEvent(tick, mob.name, ability_name, f"{mob.name} attacks the air!", room.id)]

    raw_damage = math.floor(mob.atk * 1.5)
    raw_damage = modify_source_damage(mob, raw_damage)
    pdef = target.armor.pdef + target.ring.pdef
    damage = max(1, raw_damage - pdef) if raw_damage > 0 else 0
    damage = modify_incoming_damage(target, damage)

    target.hp = max(0, target.hp - damage)
    cmd_display = ability_name.replace("_", " ")
    result = f"{mob.name} uses {cmd_display} on {target.name} for {damage} damage. ({target.name} HP: {target.hp}/{target.max_hp})"
    if target.hp <= 0:
        target.hp = 0
        target.alive = False
        result += f" {target.name} has fallen!"

    return [GameEvent(tick, mob.name, f"{ability_name} {target.name}", result, room.id)]


def _resolve_mob_aoe(
    mob: Mob, ability_name: str, room: Room, tick: int, agents: list[AgentState],
) -> list[GameEvent]:
    """Mob AoE ability: hit all agents in room."""
    targets = [a for a in agents if a.alive and a.room_id == room.id]
    if not targets:
        return [GameEvent(tick, mob.name, ability_name, f"{mob.name} attacks the air!", room.id)]

    parts = []
    for target in targets:
        raw_damage = mob.atk
        raw_damage = modify_source_damage(mob, raw_damage)
        pdef = target.armor.pdef + target.ring.pdef
        damage = max(1, raw_damage - pdef) if raw_damage > 0 else 0
        damage = modify_incoming_damage(target, damage)

        target.hp = max(0, target.hp - damage)
        part = f"{target.name} takes {damage} ({target.name} HP: {target.hp}/{target.max_hp})"
        if target.hp <= 0:
            target.hp = 0
            target.alive = False
            part += " FALLEN!"
        parts.append(part)

    cmd_display = ability_name.replace("_", " ")
    result = f"{mob.name} uses {cmd_display}! " + "; ".join(parts)
    return [GameEvent(tick, mob.name, ability_name, result, room.id)]


def _resolve_mob_dot(
    mob: Mob, ability_name: str, target_name: str, room: Room, tick: int,
    agents: list[AgentState],
) -> list[GameEvent]:
    """Mob applies a DoT (curse, poison_arrow, bleed) to an agent."""
    target = _find_agent_target(target_name, agents, room.id)
    if not target:
        return [GameEvent(tick, mob.name, ability_name, f"{mob.name} attacks the air!", room.id)]

    effect_map = {
        "curse": ("cursed", 3, 2),
        "poison_arrow": ("poisoned", 3, 2),
        "bleed": ("bleeding", 3, 2),
    }
    effect_name, duration, damage = effect_map.get(ability_name, ("cursed", 3, 2))
    apply_effect(target, StatusEffect(effect_name, mob.name, duration, value=damage))

    cmd_display = ability_name.replace("_", " ")
    result = f"{mob.name} uses {cmd_display} on {target.name}! {damage} damage/tick for {duration} ticks."
    return [GameEvent(tick, mob.name, f"{ability_name} {target.name}", result, room.id)]


def _resolve_mob_sleep(
    mob: Mob, target_name: str, room: Room, tick: int, agents: list[AgentState],
) -> list[GameEvent]:
    """Mob puts an agent to sleep."""
    target = _find_agent_target(target_name, agents, room.id)
    if not target:
        return [GameEvent(tick, mob.name, "sleep", f"{mob.name} attacks the air!", room.id)]

    apply_effect(target, StatusEffect("asleep", mob.name, 2))
    result = f"{mob.name} puts {target.name} to sleep for 2 turns!"
    return [GameEvent(tick, mob.name, f"sleep {target.name}", result, room.id)]


def _resolve_mob_heal(mob: Mob, room: Room, tick: int) -> list[GameEvent]:
    """Mob heals itself."""
    heal_amount = math.ceil(mob.max_hp * 0.2)
    old_hp = mob.hp
    mob.hp = min(mob.max_hp, mob.hp + heal_amount)
    actual = mob.hp - old_hp
    result = f"{mob.name} heals for {actual} HP. ({mob.name} HP: {mob.hp}/{mob.max_hp})"
    return [GameEvent(tick, mob.name, "heal", result, room.id)]
