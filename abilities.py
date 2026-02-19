"""Ability system — registry of all 24 abilities with resolver functions.

Each ability is a function that takes (source, target_name, room, tick, agents, rooms)
and returns a list[GameEvent]. The registry dispatches by ability name.
"""
from __future__ import annotations

import math
from typing import Any

from config import ABILITY_DEFINITIONS, CLASS_DEFINITIONS
from effects import (
    apply_effect,
    clear_debuffs,
    is_incapacitated,
    modify_incoming_damage,
    modify_outgoing_damage,
    modify_source_damage,
)
from models import AgentState, GameEvent, Item, Mob, Room, StatusEffect


# ── Helpers ──

def _agent_atk(agent: AgentState) -> int:
    return agent.weapon.atk


def _agent_mdmg(agent: AgentState) -> int:
    return agent.ring.mdmg


def _agent_pdef(agent: AgentState) -> int:
    return agent.armor.pdef + agent.ring.pdef


def _agent_mdef(agent: AgentState) -> int:
    return agent.armor.mdef + agent.ring.mdef


def _find_mob(room: Room, name: str) -> Mob | None:
    name_lower = name.lower()
    for mob in room.mobs:
        if mob.hp > 0 and name_lower in mob.name.lower():
            return mob
    return None


def _find_ally(agents: list[AgentState], agent: AgentState, name: str) -> AgentState | None:
    name_lower = name.lower()
    for a in agents:
        if a.alive and a.room_id == agent.room_id and name_lower in a.name.lower():
            return a
    return None


def _living_mobs(room: Room) -> list[Mob]:
    return [m for m in room.mobs if m.hp > 0]


def _living_allies_in_room(agents: list[AgentState], room_id: str) -> list[AgentState]:
    return [a for a in agents if a.alive and a.room_id == room_id]


def _target_failure_hint(target_name: str, room: Room, agents: list[AgentState] | None = None, agent_name: str = "") -> str:
    """Rich failure message for invalid combat target."""
    target_lower = target_name.lower()
    reason = ""

    for npc in room.npcs:
        if target_lower in npc.name.lower():
            reason = f"'{npc.name}' is an NPC, not an enemy."
            break

    if not reason and agents:
        for a in agents:
            if a.alive and a.room_id == room.id and a.name != agent_name and target_lower in a.name.lower():
                reason = f"'{a.name}' is your ally, not an enemy."
                break

    if not reason:
        for mob in room.mobs:
            if mob.hp <= 0 and target_lower in mob.name.lower():
                reason = f"'{mob.name}' is already dead."
                break

    if not reason:
        reason = f"No enemy named '{target_name}' in this room."

    living = _living_mobs(room)
    if living:
        reason += f" Enemies here: {', '.join(m.name for m in living)}."
    else:
        reason += " No enemies in this room."

    return reason


def _mob_dies(mob: Mob, room: Room, result_parts: list[str]) -> None:
    """Handle mob death: mark slain, drop loot."""
    result_parts.append(f"{mob.name} is slain!")
    if mob.loot:
        for item in mob.loot:
            room.items.append(item)
        loot_names = ", ".join(i.name for i in mob.loot)
        result_parts.append(f"Loot dropped: {loot_names}.")


def _apply_damage_to_mob(mob: Mob, damage: int, room: Room) -> tuple[int, list[str]]:
    """Apply damage to mob, handle death. Returns (actual_damage, extra_result_parts)."""
    actual = min(mob.hp, damage)
    mob.hp = max(0, mob.hp - damage)
    parts = []
    if mob.hp <= 0:
        mob.alive = False
        _mob_dies(mob, room, parts)
    return actual, parts


def _apply_damage_to_agent(agent: AgentState, damage: int) -> list[str]:
    """Apply damage to agent, handle death. Returns extra result parts."""
    agent.hp = max(0, agent.hp - damage)
    parts = []
    if agent.hp <= 0:
        agent.hp = 0
        agent.alive = False
        parts.append(f"{agent.name} has fallen!")
    return parts


# ── Cost checking ──

def can_afford(source: AgentState, ability_name: str) -> tuple[bool, str]:
    """Check if source can afford the ability. Returns (can_afford, error_msg)."""
    defn = ABILITY_DEFINITIONS.get(ability_name)
    if not defn:
        return False, f"Unknown ability: {ability_name}"

    cost = defn["cost"]
    cost_type = defn["cost_type"]

    if cost_type == "free":
        return True, ""
    elif cost_type == "mp":
        if source.mp < cost:
            return False, f"Not enough MP ({source.mp}/{cost})."
        return True, ""
    elif cost_type == "ap":
        if source.ap < cost:
            return False, f"Not enough AP ({source.ap}/{cost})."
        return True, ""
    elif cost_type == "hp":
        if source.hp <= cost:
            return False, f"Not enough HP to sacrifice ({source.hp} HP, costs {cost})."
        return True, ""
    return False, f"Unknown cost type: {cost_type}"


def pay_cost(source: AgentState, ability_name: str) -> None:
    """Deduct the cost of an ability from source."""
    defn = ABILITY_DEFINITIONS[ability_name]
    cost = defn["cost"]
    cost_type = defn["cost_type"]

    if cost_type == "mp":
        source.mp -= cost
    elif cost_type == "ap":
        source.ap -= cost
    elif cost_type == "hp":
        source.hp -= cost


# ── Main dispatcher ──

def resolve_ability(
    source: AgentState,
    ability_name: str,
    target_name: str,
    room: Room,
    tick: int,
    agents: list[AgentState],
    rooms: dict[str, Room],
) -> list[GameEvent]:
    """Resolve an ability use. Returns list of GameEvents."""
    # Check incapacitation
    if is_incapacitated(source):
        return [GameEvent(tick, source.name, ability_name,
                         f"{source.name} is asleep and cannot act!", source.room_id)]

    # Check cost
    affordable, err = can_afford(source, ability_name)
    if not affordable:
        return [GameEvent(tick, source.name, ability_name, err, source.room_id)]

    # Dispatch to resolver
    resolver = ABILITY_REGISTRY.get(ability_name)
    if not resolver:
        return [GameEvent(tick, source.name, ability_name,
                         f"Unknown ability: {ability_name}", source.room_id)]

    return resolver(source, target_name, room, tick, agents, rooms)


# ── Individual ability resolvers ──

def _resolve_attack(source, target_name, room, tick, agents, rooms):
    mob = _find_mob(room, target_name)
    if not mob:
        hint = _target_failure_hint(target_name, room, agents, source.name)
        return [GameEvent(tick, source.name, f"attack {target_name}", hint, source.room_id)]

    raw_damage = max(1, _agent_atk(source))
    damage = modify_outgoing_damage(source, raw_damage)
    damage = max(1, damage - mob.pdef)
    mob.hp = max(0, mob.hp - damage)

    result = f"{source.name} attacks {mob.name} for {damage} damage. ({mob.name} HP: {mob.hp}/{mob.max_hp})"
    if mob.hp <= 0:
        mob.alive = False
        result += f" {mob.name} is slain!"
        if mob.loot:
            for item in mob.loot:
                room.items.append(item)
            result += f" Loot dropped: {', '.join(i.name for i in mob.loot)}."

    return [GameEvent(tick, source.name, f"attack {mob.name}", result, source.room_id)]


def _resolve_cleave(source, target_name, room, tick, agents, rooms):
    pay_cost(source, "cleave")
    mobs = _living_mobs(room)
    if not mobs:
        return [GameEvent(tick, source.name, "cleave", "No enemies in this room.", source.room_id)]

    parts = []
    for mob in mobs:
        raw = max(1, _agent_atk(source))
        damage = modify_outgoing_damage(source, raw)
        damage = max(1, damage - mob.pdef)
        mob.hp = max(0, mob.hp - damage)
        part = f"{mob.name} takes {damage} ({mob.name} HP: {mob.hp}/{mob.max_hp})"
        if mob.hp <= 0:
            mob.alive = False
            part += " SLAIN!"
            if mob.loot:
                for item in mob.loot:
                    room.items.append(item)
        parts.append(part)

    result = f"{source.name} cleaves all enemies! " + "; ".join(parts)
    return [GameEvent(tick, source.name, "cleave", result, source.room_id)]


def _resolve_taunt(source, target_name, room, tick, agents, rooms):
    pay_cost(source, "taunt")
    mobs = _living_mobs(room)
    for mob in mobs:
        apply_effect(mob, StatusEffect("taunted", source.name, 1))

    if mobs:
        result = f"{source.name} taunts all enemies! They must target {source.name} next turn."
    else:
        result = f"{source.name} taunts... but there are no enemies here."
    return [GameEvent(tick, source.name, "taunt", result, source.room_id)]


def _resolve_defend(source, target_name, room, tick, agents, rooms):
    pay_cost(source, "defend")
    apply_effect(source, StatusEffect("defending", source.name, 1))
    result = f"{source.name} takes a defensive stance. Incoming damage reduced by 50% this tick."
    return [GameEvent(tick, source.name, "defend", result, source.room_id)]


def _resolve_rally(source, target_name, room, tick, agents, rooms):
    pay_cost(source, "rally")
    allies = _living_allies_in_room(agents, source.room_id)
    names = []
    for ally in allies:
        if ally.name != source.name:
            apply_effect(ally, StatusEffect("rallied", source.name, -1, value=2))
            names.append(ally.name)

    if names:
        result = f"{source.name} rallies allies! {', '.join(names)} deal +2 damage on next hit."
    else:
        result = f"{source.name} rallies... but no allies are here."
    return [GameEvent(tick, source.name, "rally", result, source.room_id)]


def _resolve_smite(source, target_name, room, tick, agents, rooms):
    mob = _find_mob(room, target_name)
    if not mob:
        hint = _target_failure_hint(target_name, room, agents, source.name)
        return [GameEvent(tick, source.name, f"smite {target_name}", hint, source.room_id)]

    pay_cost(source, "smite")
    raw = max(1, math.floor(_agent_atk(source) * 1.5))
    damage = modify_outgoing_damage(source, raw)
    damage = max(1, damage - mob.mdef)
    mob.hp = max(0, mob.hp - damage)

    result = f"{source.name} smites {mob.name} for {damage} holy damage. ({mob.name} HP: {mob.hp}/{mob.max_hp})"
    if mob.hp <= 0:
        mob.alive = False
        result += f" {mob.name} is slain!"
        if mob.loot:
            for item in mob.loot:
                room.items.append(item)

    return [GameEvent(tick, source.name, f"smite {mob.name}", result, source.room_id)]


def _resolve_lay_on_hands(source, target_name, room, tick, agents, rooms):
    target = source
    if target_name:
        found = _find_ally(agents, source, target_name)
        if found:
            target = found
        else:
            return [GameEvent(tick, source.name, f"lay_on_hands {target_name}",
                             f"No ally named '{target_name}' here.", source.room_id)]

    pay_cost(source, "lay_on_hands")
    heal_amount = math.ceil(target.max_hp * 0.40)
    old_hp = target.hp
    target.hp = min(target.max_hp, target.hp + heal_amount)
    actual = target.hp - old_hp

    if target is source:
        result = f"{source.name} lays on hands, healing self for {actual} HP. (HP: {source.hp}/{source.max_hp})"
    else:
        result = f"{source.name} lays on hands on {target.name} for {actual} HP. ({target.name} HP: {target.hp}/{target.max_hp})"
    return [GameEvent(tick, source.name, f"lay_on_hands {target.name}", result, source.room_id)]


def _resolve_shield(source, target_name, room, tick, agents, rooms):
    if not target_name:
        return [GameEvent(tick, source.name, "shield", "Shield requires an ally target.", source.room_id)]
    target = _find_ally(agents, source, target_name)
    if not target or target is source:
        return [GameEvent(tick, source.name, f"shield {target_name}",
                         f"No ally named '{target_name}' here (cannot shield yourself).", source.room_id)]

    pay_cost(source, "shield")
    apply_effect(target, StatusEffect("shielded", source.name, -1))
    result = f"{source.name} shields {target.name}! Next attack on {target.name} will be redirected to {source.name}."
    return [GameEvent(tick, source.name, f"shield {target.name}", result, source.room_id)]


def _resolve_consecrate(source, target_name, room, tick, agents, rooms):
    pay_cost(source, "consecrate")
    mobs = _living_mobs(room)
    if not mobs:
        return [GameEvent(tick, source.name, "consecrate", "No enemies in this room.", source.room_id)]

    parts = []
    for mob in mobs:
        raw = max(1, _agent_atk(source))
        damage = modify_outgoing_damage(source, raw)
        damage = max(1, damage - mob.mdef)
        mob.hp = max(0, mob.hp - damage)
        part = f"{mob.name} takes {damage} ({mob.name} HP: {mob.hp}/{mob.max_hp})"
        if mob.hp <= 0:
            mob.alive = False
            part += " SLAIN!"
            if mob.loot:
                for item in mob.loot:
                    room.items.append(item)
        parts.append(part)

    result = f"{source.name} consecrates the ground! " + "; ".join(parts)
    return [GameEvent(tick, source.name, "consecrate", result, source.room_id)]


def _resolve_missile(source, target_name, room, tick, agents, rooms):
    mob = _find_mob(room, target_name)
    if not mob:
        hint = _target_failure_hint(target_name, room, agents, source.name)
        return [GameEvent(tick, source.name, f"missile {target_name}", hint, source.room_id)]

    pay_cost(source, "missile")
    raw = max(1, _agent_mdmg(source))
    damage = modify_outgoing_damage(source, raw)
    damage = max(1, damage - mob.mdef)
    mob.hp = max(0, mob.hp - damage)

    result = f"{source.name} casts missile at {mob.name} for {damage} magic damage. ({mob.name} HP: {mob.hp}/{mob.max_hp})"
    if mob.hp <= 0:
        mob.alive = False
        result += f" {mob.name} is slain!"
        if mob.loot:
            for item in mob.loot:
                room.items.append(item)

    return [GameEvent(tick, source.name, f"missile {mob.name}", result, source.room_id)]


def _resolve_arcane_storm(source, target_name, room, tick, agents, rooms):
    pay_cost(source, "arcane_storm")
    mobs = _living_mobs(room)
    if not mobs:
        return [GameEvent(tick, source.name, "arcane_storm", "No enemies in this room.", source.room_id)]

    parts = []
    for mob in mobs:
        raw = max(1, _agent_mdmg(source) * 2)
        damage = modify_outgoing_damage(source, raw)
        damage = max(1, damage - mob.mdef)
        mob.hp = max(0, mob.hp - damage)
        part = f"{mob.name} takes {damage} ({mob.name} HP: {mob.hp}/{mob.max_hp})"
        if mob.hp <= 0:
            mob.alive = False
            part += " SLAIN!"
            if mob.loot:
                for item in mob.loot:
                    room.items.append(item)
        parts.append(part)

    result = f"{source.name} casts arcane storm! " + "; ".join(parts)
    return [GameEvent(tick, source.name, "arcane_storm", result, source.room_id)]


def _resolve_curse(source, target_name, room, tick, agents, rooms):
    mob = _find_mob(room, target_name)
    if not mob:
        hint = _target_failure_hint(target_name, room, agents, source.name)
        return [GameEvent(tick, source.name, f"curse {target_name}", hint, source.room_id)]

    pay_cost(source, "curse")
    apply_effect(mob, StatusEffect("cursed", source.name, 3, value=2))
    result = f"{source.name} curses {mob.name}! It will take 2 damage/tick for 3 ticks."
    return [GameEvent(tick, source.name, f"curse {mob.name}", result, source.room_id)]


def _resolve_barrier(source, target_name, room, tick, agents, rooms):
    target = source
    if target_name:
        found = _find_ally(agents, source, target_name)
        if found:
            target = found
        else:
            return [GameEvent(tick, source.name, f"barrier {target_name}",
                             f"No ally named '{target_name}' here.", source.room_id)]

    pay_cost(source, "barrier")
    apply_effect(target, StatusEffect("barrier", source.name, -1, value=8))

    if target is source:
        result = f"{source.name} creates a barrier on self, absorbing up to 8 damage."
    else:
        result = f"{source.name} creates a barrier on {target.name}, absorbing up to 8 damage."
    return [GameEvent(tick, source.name, f"barrier {target.name}", result, source.room_id)]


def _resolve_heal(source, target_name, room, tick, agents, rooms):
    target = source
    if target_name:
        found = _find_ally(agents, source, target_name)
        if found:
            target = found
        else:
            return [GameEvent(tick, source.name, f"heal {target_name}",
                             f"No ally named '{target_name}' here.", source.room_id)]

    pay_cost(source, "heal")
    heal_amount = math.ceil(target.max_hp * 0.30)
    old_hp = target.hp
    target.hp = min(target.max_hp, target.hp + heal_amount)
    actual = target.hp - old_hp

    if target is source:
        result = f"{source.name} heals self for {actual} HP. (HP: {source.hp}/{source.max_hp})"
    else:
        result = f"{source.name} heals {target.name} for {actual} HP. ({target.name} HP: {target.hp}/{target.max_hp})"
    action_label = f"heal {target.name}" if target is not source else "heal"
    return [GameEvent(tick, source.name, action_label, result, source.room_id)]


def _resolve_ward(source, target_name, room, tick, agents, rooms):
    target = source
    if target_name:
        found = _find_ally(agents, source, target_name)
        if found:
            target = found
        else:
            return [GameEvent(tick, source.name, f"ward {target_name}",
                             f"No ally named '{target_name}' here.", source.room_id)]

    pay_cost(source, "ward")
    apply_effect(target, StatusEffect("warded", source.name, 3, value=3))

    if target is source:
        result = f"{source.name} wards self, reducing incoming damage by 3 for 3 ticks."
    else:
        result = f"{source.name} wards {target.name}, reducing incoming damage by 3 for 3 ticks."
    return [GameEvent(tick, source.name, f"ward {target.name}", result, source.room_id)]


def _resolve_holy_bolt(source, target_name, room, tick, agents, rooms):
    mob = _find_mob(room, target_name)
    if not mob:
        hint = _target_failure_hint(target_name, room, agents, source.name)
        return [GameEvent(tick, source.name, f"holy_bolt {target_name}", hint, source.room_id)]

    pay_cost(source, "holy_bolt")
    raw = max(1, math.floor(_agent_mdmg(source) * 1.5))
    damage = modify_outgoing_damage(source, raw)
    damage = max(1, damage - mob.mdef)
    mob.hp = max(0, mob.hp - damage)

    result = f"{source.name} casts holy bolt at {mob.name} for {damage} holy damage. ({mob.name} HP: {mob.hp}/{mob.max_hp})"
    if mob.hp <= 0:
        mob.alive = False
        result += f" {mob.name} is slain!"
        if mob.loot:
            for item in mob.loot:
                room.items.append(item)

    return [GameEvent(tick, source.name, f"holy_bolt {mob.name}", result, source.room_id)]


def _resolve_cure(source, target_name, room, tick, agents, rooms):
    target = source
    if target_name:
        found = _find_ally(agents, source, target_name)
        if found:
            target = found
        else:
            return [GameEvent(tick, source.name, f"cure {target_name}",
                             f"No ally named '{target_name}' here.", source.room_id)]

    pay_cost(source, "cure")
    cleared = clear_debuffs(target)

    if cleared:
        if target is source:
            result = f"{source.name} cures self, removing: {', '.join(cleared)}."
        else:
            result = f"{source.name} cures {target.name}, removing: {', '.join(cleared)}."
    else:
        if target is source:
            result = f"{source.name} cures self, but no debuffs to remove."
        else:
            result = f"{source.name} cures {target.name}, but no debuffs to remove."
    return [GameEvent(tick, source.name, f"cure {target.name}", result, source.room_id)]


def _resolve_aimed_shot(source, target_name, room, tick, agents, rooms):
    mob = _find_mob(room, target_name)
    if not mob:
        hint = _target_failure_hint(target_name, room, agents, source.name)
        return [GameEvent(tick, source.name, f"aimed_shot {target_name}", hint, source.room_id)]

    pay_cost(source, "aimed_shot")
    raw = max(1, _agent_atk(source) * 2)
    damage = modify_outgoing_damage(source, raw)
    damage = max(1, damage - mob.pdef)
    mob.hp = max(0, mob.hp - damage)

    result = f"{source.name} fires an aimed shot at {mob.name} for {damage} damage. ({mob.name} HP: {mob.hp}/{mob.max_hp})"
    if mob.hp <= 0:
        mob.alive = False
        result += f" {mob.name} is slain!"
        if mob.loot:
            for item in mob.loot:
                room.items.append(item)

    return [GameEvent(tick, source.name, f"aimed_shot {mob.name}", result, source.room_id)]


def _resolve_volley(source, target_name, room, tick, agents, rooms):
    pay_cost(source, "volley")
    mobs = _living_mobs(room)
    if not mobs:
        return [GameEvent(tick, source.name, "volley", "No enemies in this room.", source.room_id)]

    parts = []
    for mob in mobs:
        raw = max(1, _agent_atk(source))
        damage = modify_outgoing_damage(source, raw)
        damage = max(1, damage - mob.pdef)
        mob.hp = max(0, mob.hp - damage)
        part = f"{mob.name} takes {damage} ({mob.name} HP: {mob.hp}/{mob.max_hp})"
        if mob.hp <= 0:
            mob.alive = False
            part += " SLAIN!"
            if mob.loot:
                for item in mob.loot:
                    room.items.append(item)
        parts.append(part)

    result = f"{source.name} fires a volley! " + "; ".join(parts)
    return [GameEvent(tick, source.name, "volley", result, source.room_id)]


def _resolve_poison_arrow(source, target_name, room, tick, agents, rooms):
    mob = _find_mob(room, target_name)
    if not mob:
        hint = _target_failure_hint(target_name, room, agents, source.name)
        return [GameEvent(tick, source.name, f"poison_arrow {target_name}", hint, source.room_id)]

    pay_cost(source, "poison_arrow")
    apply_effect(mob, StatusEffect("poisoned", source.name, 3, value=2))
    result = f"{source.name} fires a poison arrow at {mob.name}! It will take 2 damage/tick for 3 ticks."
    return [GameEvent(tick, source.name, f"poison_arrow {mob.name}", result, source.room_id)]


def _resolve_sleep(source, target_name, room, tick, agents, rooms):
    mob = _find_mob(room, target_name)
    if not mob:
        hint = _target_failure_hint(target_name, room, agents, source.name)
        return [GameEvent(tick, source.name, f"sleep {target_name}", hint, source.room_id)]

    pay_cost(source, "sleep")
    apply_effect(mob, StatusEffect("asleep", source.name, 2))
    result = f"{source.name} puts {mob.name} to sleep! It will skip its next 2 turns."
    return [GameEvent(tick, source.name, f"sleep {mob.name}", result, source.room_id)]


def _resolve_backstab(source, target_name, room, tick, agents, rooms):
    mob = _find_mob(room, target_name)
    if not mob:
        hint = _target_failure_hint(target_name, room, agents, source.name)
        return [GameEvent(tick, source.name, f"backstab {target_name}", hint, source.room_id)]

    pay_cost(source, "backstab")
    raw = max(1, math.floor(_agent_atk(source) * 2.5))
    damage = modify_outgoing_damage(source, raw)
    # Backstab ignores defense
    mob.hp = max(0, mob.hp - damage)

    result = f"{source.name} backstabs {mob.name} for {damage} damage (ignores defense). ({mob.name} HP: {mob.hp}/{mob.max_hp})"
    if mob.hp <= 0:
        mob.alive = False
        result += f" {mob.name} is slain!"
        if mob.loot:
            for item in mob.loot:
                room.items.append(item)

    return [GameEvent(tick, source.name, f"backstab {mob.name}", result, source.room_id)]


def _resolve_bleed(source, target_name, room, tick, agents, rooms):
    mob = _find_mob(room, target_name)
    if not mob:
        hint = _target_failure_hint(target_name, room, agents, source.name)
        return [GameEvent(tick, source.name, f"bleed {target_name}", hint, source.room_id)]

    pay_cost(source, "bleed")
    apply_effect(mob, StatusEffect("bleeding", source.name, 3, value=2))
    result = f"{source.name} causes {mob.name} to bleed! It will take 2 damage/tick for 3 ticks."
    return [GameEvent(tick, source.name, f"bleed {mob.name}", result, source.room_id)]


def _resolve_evade(source, target_name, room, tick, agents, rooms):
    pay_cost(source, "evade")
    apply_effect(source, StatusEffect("evading", source.name, -1))
    result = f"{source.name} prepares to evade. The next attack against {source.name} will deal 0 damage."
    return [GameEvent(tick, source.name, "evade", result, source.room_id)]


def _resolve_smoke_bomb(source, target_name, room, tick, agents, rooms):
    pay_cost(source, "smoke_bomb")
    mobs = _living_mobs(room)
    for mob in mobs:
        apply_effect(mob, StatusEffect("blinded", source.name, 2, value=3))

    if mobs:
        result = f"{source.name} throws a smoke bomb! All enemies deal -3 damage for 2 ticks."
    else:
        result = f"{source.name} throws a smoke bomb... but there are no enemies here."
    return [GameEvent(tick, source.name, "smoke_bomb", result, source.room_id)]


# ── Registry ──

ABILITY_REGISTRY = {
    "attack": _resolve_attack,
    "cleave": _resolve_cleave,
    "taunt": _resolve_taunt,
    "defend": _resolve_defend,
    "rally": _resolve_rally,
    "smite": _resolve_smite,
    "lay_on_hands": _resolve_lay_on_hands,
    "shield": _resolve_shield,
    "consecrate": _resolve_consecrate,
    "missile": _resolve_missile,
    "arcane_storm": _resolve_arcane_storm,
    "curse": _resolve_curse,
    "barrier": _resolve_barrier,
    "heal": _resolve_heal,
    "ward": _resolve_ward,
    "holy_bolt": _resolve_holy_bolt,
    "cure": _resolve_cure,
    "aimed_shot": _resolve_aimed_shot,
    "volley": _resolve_volley,
    "poison_arrow": _resolve_poison_arrow,
    "sleep": _resolve_sleep,
    "backstab": _resolve_backstab,
    "bleed": _resolve_bleed,
    "evade": _resolve_evade,
    "smoke_bomb": _resolve_smoke_bomb,
}
