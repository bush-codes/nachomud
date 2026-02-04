from __future__ import annotations

import math

from config import HEAL_PERCENT, POISON_DAMAGE, POISON_DURATION, SPELL_COSTS
from models import AgentState, GameEvent, Mob, Room


def _agent_pdef(agent: AgentState) -> int:
    return agent.armor.pdef + agent.ring.pdef


def _agent_mdef(agent: AgentState) -> int:
    return agent.armor.mdef + agent.ring.mdef


def _agent_atk(agent: AgentState) -> int:
    return agent.weapon.atk


def _agent_mdmg(agent: AgentState) -> int:
    return agent.ring.mdmg


def _find_mob(room: Room, mob_name: str) -> Mob | None:
    mob_name_lower = mob_name.lower()
    for mob in room.mobs:
        if mob.hp > 0 and mob_name_lower in mob.name.lower():
            return mob
    return None


def resolve_attack(agent: AgentState, room: Room, target_name: str, tick: int) -> list[GameEvent]:
    events = []
    mob = _find_mob(room, target_name)
    if mob is None:
        events.append(GameEvent(tick, agent.name, f"attack {target_name}",
                                f"No living mob named '{target_name}' here.", agent.room_id))
        return events

    damage = max(0, _agent_atk(agent) - 0)  # mobs have no pdef
    mob.hp = max(0, mob.hp - damage)
    result = f"{agent.name} attacks {mob.name} for {damage} damage. ({mob.name} HP: {mob.hp}/{mob.max_hp})"

    if mob.hp <= 0:
        result += f" {mob.name} is slain!"
        if mob.loot:
            for item in mob.loot:
                room.items.append(item)
            loot_names = ", ".join(i.name for i in mob.loot)
            result += f" Loot dropped: {loot_names}."
    events.append(GameEvent(tick, agent.name, f"attack {mob.name}", result, agent.room_id))

    # Mob counterattack
    if mob.hp > 0:
        counter = mob_counterattack(agent, mob, tick)
        events.extend(counter)

    return events


def resolve_missile(agent: AgentState, room: Room, target_name: str, tick: int) -> list[GameEvent]:
    events = []
    cost = SPELL_COSTS["missile"]
    if agent.mp < cost:
        events.append(GameEvent(tick, agent.name, f"missile {target_name}",
                                f"Not enough MP ({agent.mp}/{cost}).", agent.room_id))
        return events

    mob = _find_mob(room, target_name)
    if mob is None:
        events.append(GameEvent(tick, agent.name, f"missile {target_name}",
                                f"No living mob named '{target_name}' here.", agent.room_id))
        return events

    agent.mp -= cost
    damage = max(1, _agent_mdmg(agent) - mob.mdef)
    mob.hp = max(0, mob.hp - damage)
    result = f"{agent.name} casts missile at {mob.name} for {damage} magic damage. ({mob.name} HP: {mob.hp}/{mob.max_hp})"

    if mob.hp <= 0:
        result += f" {mob.name} is slain!"
        if mob.loot:
            for item in mob.loot:
                room.items.append(item)
            loot_names = ", ".join(i.name for i in mob.loot)
            result += f" Loot dropped: {loot_names}."
    events.append(GameEvent(tick, agent.name, f"missile {mob.name}", result, agent.room_id))

    if mob.hp > 0:
        counter = mob_counterattack(agent, mob, tick)
        events.extend(counter)

    return events


def resolve_fireball(agent: AgentState, room: Room, tick: int) -> list[GameEvent]:
    events = []
    cost = SPELL_COSTS["fireball"]
    if agent.mp < cost:
        events.append(GameEvent(tick, agent.name, "fireball",
                                f"Not enough MP ({agent.mp}/{cost}).", agent.room_id))
        return events

    agent.mp -= cost
    base_dmg = _agent_mdmg(agent) * 2
    living_mobs = [m for m in room.mobs if m.hp > 0]
    if not living_mobs:
        events.append(GameEvent(tick, agent.name, "fireball",
                                "No mobs to target.", agent.room_id))
        return events

    parts = []
    for mob in living_mobs:
        damage = max(1, base_dmg - mob.mdef)
        mob.hp = max(0, mob.hp - damage)
        parts.append(f"{mob.name} takes {damage} ({mob.name} HP: {mob.hp}/{mob.max_hp})")
        if mob.hp <= 0:
            parts[-1] += " SLAIN!"
            if mob.loot:
                for item in mob.loot:
                    room.items.append(item)

    result = f"{agent.name} casts fireball! " + "; ".join(parts)
    events.append(GameEvent(tick, agent.name, "fireball", result, agent.room_id))

    # Surviving mobs counterattack
    for mob in living_mobs:
        if mob.hp > 0:
            counter = mob_counterattack(agent, mob, tick)
            events.extend(counter)

    return events


def resolve_poison(agent: AgentState, room: Room, target_name: str, tick: int) -> list[GameEvent]:
    events = []
    cost = SPELL_COSTS["poison"]
    if agent.mp < cost:
        events.append(GameEvent(tick, agent.name, f"poison {target_name}",
                                f"Not enough MP ({agent.mp}/{cost}).", agent.room_id))
        return events

    mob = _find_mob(room, target_name)
    if mob is None:
        events.append(GameEvent(tick, agent.name, f"poison {target_name}",
                                f"No living mob named '{target_name}' here.", agent.room_id))
        return events

    agent.mp -= cost
    mob.poison_remaining = POISON_DURATION
    result = f"{agent.name} poisons {mob.name}! It will take {POISON_DAMAGE} damage/tick for {POISON_DURATION} ticks."
    events.append(GameEvent(tick, agent.name, f"poison {mob.name}", result, agent.room_id))
    return events


def resolve_heal(agent: AgentState, tick: int) -> list[GameEvent]:
    events = []
    cost = SPELL_COSTS["heal"]
    if agent.mp < cost:
        events.append(GameEvent(tick, agent.name, "heal",
                                f"Not enough MP ({agent.mp}/{cost}).", agent.room_id))
        return events

    agent.mp -= cost
    heal_amount = math.ceil(agent.max_hp * HEAL_PERCENT)
    old_hp = agent.hp
    agent.hp = min(agent.max_hp, agent.hp + heal_amount)
    actual = agent.hp - old_hp
    result = f"{agent.name} heals for {actual} HP. (HP: {agent.hp}/{agent.max_hp})"
    events.append(GameEvent(tick, agent.name, "heal", result, agent.room_id))
    return events


def mob_counterattack(agent: AgentState, mob: Mob, tick: int) -> list[GameEvent]:
    events = []
    pdef = _agent_pdef(agent)
    damage = mob.atk - pdef
    if damage <= 0 and mob.atk > 0:
        damage = 1
    damage = max(0, damage)
    agent.hp -= damage
    result = f"{mob.name} retaliates against {agent.name} for {damage} damage. ({agent.name} HP: {agent.hp}/{agent.max_hp})"
    if agent.hp <= 0:
        agent.hp = 0
        agent.alive = False
        result += f" {agent.name} has fallen!"
    events.append(GameEvent(tick, mob.name, "counterattack", result, agent.room_id))
    return events


def tick_poison(room: Room, tick: int) -> list[GameEvent]:
    events = []
    for mob in room.mobs:
        if mob.poison_remaining > 0 and mob.hp > 0:
            mob.hp = max(0, mob.hp - POISON_DAMAGE)
            mob.poison_remaining -= 1
            result = f"{mob.name} takes {POISON_DAMAGE} poison damage. ({mob.name} HP: {mob.hp}/{mob.max_hp})"
            if mob.hp <= 0:
                result += f" {mob.name} succumbs to poison!"
                if mob.loot:
                    for item in mob.loot:
                        room.items.append(item)
            events.append(GameEvent(tick, "poison", "tick", result, room.id))
    return events
