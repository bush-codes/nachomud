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


def _target_failure_hint(target_name: str, room: Room, agents: list["AgentState"] | None = None, agent_name: str = "") -> str:
    """Build a rich failure message explaining why a combat target wasn't found."""
    target_lower = target_name.lower()
    reason = ""

    # Check if target is an NPC in the room
    for npc in room.npcs:
        if target_lower in npc.name.lower():
            reason = f"'{npc.name}' is an NPC, not an enemy. Use 'tell {npc.name} <message>' to talk."
            break

    # Check if target is an ally in the room
    if not reason and agents:
        for a in agents:
            if a.alive and a.room_id == room.id and a.name != agent_name and target_lower in a.name.lower():
                reason = f"'{a.name}' is your ally, not an enemy."
                break

    # Check if target is a dead mob in the room
    if not reason:
        for mob in room.mobs:
            if mob.hp <= 0 and target_lower in mob.name.lower():
                reason = f"'{mob.name}' is already dead."
                break

    # Check if target is an item on the ground
    if not reason:
        for item in room.items:
            if target_lower in item.name.lower():
                reason = f"'{item.name}' is an item, not an enemy. Use 'get {item.name}' to pick it up."
                break

    if not reason:
        reason = f"No enemy named '{target_name}' in this room."

    # Always append what's actually here
    living_mobs = [m for m in room.mobs if m.hp > 0]
    if living_mobs:
        reason += f" Enemies here: {', '.join(m.name for m in living_mobs)}."
    else:
        reason += " No enemies in this room."

    return reason


def _no_mobs_hint(room: Room) -> str:
    """Build a rich failure message for AoE spells when no mobs are present."""
    return "No enemies in this room."


def _heal_failure_hint(target_name: str, agent: AgentState, allies: list["AgentState"] | None = None, room: Room | None = None) -> str:
    """Build a rich failure message explaining why a heal target wasn't found."""
    target_lower = target_name.lower()
    reason = ""

    # Check if target is an NPC in the room
    if room:
        for npc in room.npcs:
            if target_lower in npc.name.lower():
                reason = f"'{npc.name}' is an NPC, not an ally. You can only heal allies in your room."
                break

    # Check if target is a mob
    if not reason and room:
        for mob in room.mobs:
            if target_lower in mob.name.lower():
                reason = f"'{mob.name}' is an enemy, not an ally. Use 'attack' or spells to fight enemies."
                break

    if not reason:
        reason = f"No ally named '{target_name}' here."

    # Always append who can actually be healed
    allies_here = []
    if allies:
        allies_here = [a.name for a in allies if a.alive and a.room_id == agent.room_id and a.name != agent.name]
    if allies_here:
        reason += f" Allies in this room: {', '.join(allies_here)}, or yourself."
    else:
        reason += " No allies in this room. You can heal yourself."

    return reason


def resolve_attack(agent: AgentState, room: Room, target_name: str, tick: int, agents: list[AgentState] | None = None) -> list[GameEvent]:
    events = []
    mob = _find_mob(room, target_name)
    if mob is None:
        hint = _target_failure_hint(target_name, room, agents, agent.name)
        events.append(GameEvent(tick, agent.name, f"attack {target_name}", hint, agent.room_id))
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


def resolve_missile(agent: AgentState, room: Room, target_name: str, tick: int, agents: list[AgentState] | None = None) -> list[GameEvent]:
    events = []
    cost = SPELL_COSTS["missile"]
    if agent.mp < cost:
        events.append(GameEvent(tick, agent.name, f"missile {target_name}",
                                f"Not enough MP ({agent.mp}/{cost}).", agent.room_id))
        return events

    mob = _find_mob(room, target_name)
    if mob is None:
        hint = _target_failure_hint(target_name, room, agents, agent.name)
        events.append(GameEvent(tick, agent.name, f"missile {target_name}", hint, agent.room_id))
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
        hint = _no_mobs_hint(room)
        events.append(GameEvent(tick, agent.name, "fireball", hint, agent.room_id))
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


def resolve_poison(agent: AgentState, room: Room, target_name: str, tick: int, agents: list[AgentState] | None = None) -> list[GameEvent]:
    events = []
    cost = SPELL_COSTS["poison"]
    if agent.mp < cost:
        events.append(GameEvent(tick, agent.name, f"poison {target_name}",
                                f"Not enough MP ({agent.mp}/{cost}).", agent.room_id))
        return events

    mob = _find_mob(room, target_name)
    if mob is None:
        hint = _target_failure_hint(target_name, room, agents, agent.name)
        events.append(GameEvent(tick, agent.name, f"poison {target_name}", hint, agent.room_id))
        return events

    agent.mp -= cost
    mob.poison_remaining = POISON_DURATION
    result = f"{agent.name} poisons {mob.name}! It will take {POISON_DAMAGE} damage/tick for {POISON_DURATION} ticks."
    events.append(GameEvent(tick, agent.name, f"poison {mob.name}", result, agent.room_id))
    return events


def resolve_heal(agent: AgentState, tick: int, target_name: str = "", allies: list[AgentState] | None = None, room: Room | None = None) -> list[GameEvent]:
    events = []
    cost = SPELL_COSTS["heal"]
    if agent.mp < cost:
        events.append(GameEvent(tick, agent.name, "heal",
                                f"Not enough MP ({agent.mp}/{cost}).", agent.room_id))
        return events

    # Find target — default to self
    target = agent
    if target_name:
        target_lower = target_name.lower()
        # Check if targeting self
        if target_lower not in agent.name.lower():
            # Search allies in the same room
            found = None
            for a in (allies or []):
                if a.alive and a.room_id == agent.room_id and target_lower in a.name.lower():
                    found = a
                    break
            if found:
                target = found
            else:
                hint = _heal_failure_hint(target_name, agent, allies, room)
                events.append(GameEvent(tick, agent.name, f"heal {target_name}",
                                        hint, agent.room_id))
                return events

    agent.mp -= cost
    heal_amount = math.ceil(target.max_hp * HEAL_PERCENT)
    old_hp = target.hp
    target.hp = min(target.max_hp, target.hp + heal_amount)
    actual = target.hp - old_hp
    if target is agent:
        result = f"{agent.name} heals self for {actual} HP. (HP: {agent.hp}/{agent.max_hp})"
    else:
        result = f"{agent.name} heals {target.name} for {actual} HP. ({target.name} HP: {target.hp}/{target.max_hp})"
    action_label = f"heal {target.name}" if target is not agent else "heal"
    events.append(GameEvent(tick, agent.name, action_label, result, agent.room_id))
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
