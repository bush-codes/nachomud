"""Generic buff/debuff system using StatusEffect dataclass.

Effects are stored on AgentState.status_effects and Mob.status_effects.
Both use the same StatusEffect dataclass and the same functions here.
"""
from __future__ import annotations

import math
from typing import Protocol

from models import GameEvent, StatusEffect


class HasEffects(Protocol):
    """Any entity with name, hp, max_hp, alive, and status_effects."""
    name: str
    hp: int
    max_hp: int
    alive: bool
    status_effects: list[StatusEffect]


# ── Effect names by category ──

BUFFS = {"defending", "warded", "rallied", "barrier", "evading", "shielded"}
DEBUFFS = {"taunted", "cursed", "poisoned", "bleeding", "asleep", "blinded"}
DOT_EFFECTS = {"cursed", "poisoned", "bleeding"}
CONSUMABLE_EFFECTS = {"evading", "rallied", "shielded"}  # removed on first use


def apply_effect(target: HasEffects, effect: StatusEffect) -> None:
    """Apply a status effect. Refreshes (replaces) if already present — no stacking."""
    for i, existing in enumerate(target.status_effects):
        if existing.name == effect.name:
            target.status_effects[i] = effect
            return
    target.status_effects.append(effect)


def has_effect(target: HasEffects, name: str) -> bool:
    return any(e.name == name for e in target.status_effects)


def get_effect(target: HasEffects, name: str) -> StatusEffect | None:
    for e in target.status_effects:
        if e.name == name:
            return e
    return None


def consume_effect(target: HasEffects, name: str) -> StatusEffect | None:
    """Remove and return a one-shot effect (evade, shield, rally). Returns None if not found."""
    for i, e in enumerate(target.status_effects):
        if e.name == name:
            return target.status_effects.pop(i)
    return None


def clear_debuffs(target: HasEffects) -> list[str]:
    """Remove all debuffs from target. Returns list of cleared effect names."""
    cleared = []
    remaining = []
    for e in target.status_effects:
        if e.name in DEBUFFS:
            cleared.append(e.name)
        else:
            remaining.append(e)
    target.status_effects = remaining
    return cleared


def is_incapacitated(target: HasEffects) -> bool:
    """Check if target is asleep (skips their turn)."""
    return has_effect(target, "asleep")


def tick_effects(target: HasEffects, tick: int, room_id: str = "") -> list[GameEvent]:
    """Process all effects at end of tick: DoT damage, decrement durations, remove expired.

    Returns GameEvents for any DoT damage dealt.
    """
    events = []
    remaining = []

    for effect in target.status_effects:
        # Process DoT effects
        if effect.name in DOT_EFFECTS and effect.value > 0:
            target.hp = max(0, target.hp - effect.value)
            dot_type = {
                "cursed": "curse",
                "poisoned": "poison",
                "bleeding": "bleed",
            }[effect.name]
            result = f"{target.name} takes {effect.value} {dot_type} damage. ({target.name} HP: {target.hp}/{target.max_hp})"
            if target.hp <= 0:
                target.alive = False
                result += f" {target.name} succumbs to {dot_type}!"
            events.append(GameEvent(tick, dot_type, "tick", result, room_id))

        # Decrement duration (skip consumable effects — they expire on use)
        if effect.name in CONSUMABLE_EFFECTS:
            remaining.append(effect)
        elif effect.remaining_ticks > 0:
            effect.remaining_ticks -= 1
            if effect.remaining_ticks > 0:
                remaining.append(effect)
            # else: expired, don't keep
        elif effect.remaining_ticks == -1:
            # Permanent until consumed — keep
            remaining.append(effect)

    target.status_effects = remaining
    return events


def modify_incoming_damage(target: HasEffects, raw_damage: int) -> int:
    """Apply defensive effects to incoming damage. Consumes one-shot effects.

    Order: evade (→0), defend (50%), ward (-3), blinded on source handled separately,
    barrier (absorb).
    """
    damage = raw_damage

    # Evade: next attack deals 0
    if has_effect(target, "evading"):
        consume_effect(target, "evading")
        return 0

    # Defend: 50% reduction
    if has_effect(target, "defending"):
        damage = math.ceil(damage * 0.5)

    # Ward: flat reduction
    ward = get_effect(target, "warded")
    if ward:
        damage = max(0, damage - ward.value)

    # Barrier: absorb damage
    barrier = get_effect(target, "barrier")
    if barrier and damage > 0:
        if damage >= barrier.value:
            damage -= barrier.value
            consume_effect(target, "barrier")
        else:
            barrier.value -= damage
            damage = 0

    return max(0, damage)


def modify_outgoing_damage(source: HasEffects, raw_damage: int) -> int:
    """Apply offensive effects: rally (+2, consumed), blinded (-3)."""
    damage = raw_damage

    # Rally: +2 damage, consumed after use
    if has_effect(source, "rallied"):
        consume_effect(source, "rallied")
        damage += 2

    return max(0, damage)


def modify_source_damage(source: HasEffects, raw_damage: int) -> int:
    """Apply effects on the attacker that reduce their outgoing damage (e.g., blinded)."""
    damage = raw_damage

    # Blinded: -3 damage
    blinded = get_effect(source, "blinded")
    if blinded:
        damage = max(0, damage - blinded.value)

    return damage
