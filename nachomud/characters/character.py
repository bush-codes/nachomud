"""Character construction: class + race + stats → AgentState.

Used by Phase 4 char creation flow. For Phase 1 it's just the math glue
that makes Phase 1's done-when ("construct an L1 Warrior with point-buy
and have correct HP/AC/attack bonus") work end-to-end.
"""
from __future__ import annotations

import uuid

from nachomud.rules.classes import CLASS_DEFINITIONS
from nachomud.rules.races import RACE_DEFINITIONS
from nachomud.settings import STARTING_GOLD
from nachomud.models import AgentState, Item
from nachomud.rules.stats import (
    Stats,
    apply_racial_mods,
    compute_ac,
    compute_max_hp,
    mod,
    proficiency_bonus,
)


def _make_item(spec: dict) -> Item:
    """Build an Item from a class-default equipment spec (dict)."""
    return Item(**spec)


def create_character(
    name: str,
    race: str,
    class_name: str,
    base_stats: Stats,
    *,
    level: int = 1,
    player_id: str = "",
    respawn_room: str = "",
    world_id: str = "default",
) -> AgentState:
    """Build a complete L1+ AgentState from character-creation choices.

    `base_stats` is the player's point-buy assignment (pre-racial). Racial
    modifiers are applied here. Use `validate_point_buy()` first for input.
    """
    if class_name not in CLASS_DEFINITIONS:
        raise ValueError(f"Unknown class: {class_name}")
    if race not in RACE_DEFINITIONS:
        raise ValueError(f"Unknown race: {race}")

    class_def = CLASS_DEFINITIONS[class_name]
    race_def = RACE_DEFINITIONS[race]

    final_stats = apply_racial_mods(base_stats, race_def["stat_mods"])
    con_mod = mod(final_stats.CON)
    dex_mod = mod(final_stats.DEX)
    prof_bonus = proficiency_bonus(level)

    hit_die = class_def["hit_die"]
    max_hp = compute_max_hp(hit_die, con_mod, level)

    weapon = _make_item(class_def["weapon"])
    armor = _make_item(class_def["armor"])
    ring = _make_item(class_def["ring"])

    # AC = armor base + capped DEX + ring bonuses
    ac = compute_ac(
        dex_modifier=dex_mod,
        armor_base=armor.armor_base or 10,
        armor_max_dex=armor.armor_max_dex,
        misc_bonus=ring.ac_bonus,
    )

    resource_type = class_def["resource_type"]
    resource_max = class_def["resource_max"]
    if resource_type == "mp":
        mp = max_mp = resource_max
        ap = max_ap = 0
    elif resource_type == "ap":
        mp = max_mp = 0
        ap = max_ap = resource_max
    else:
        mp = max_mp = 0
        ap = max_ap = 0

    # Starting abilities + level-gated unlocks
    abilities = list(class_def["starting_abilities"])
    for unlock_level, ability in class_def["ability_unlocks"].items():
        if level >= unlock_level and ability not in abilities:
            abilities.append(ability)

    return AgentState(
        name=name,
        personality="",  # filled in elsewhere
        agent_class=class_name,
        race=race,
        level=level,
        xp=0,
        proficiency_bonus=prof_bonus,
        hit_die=hit_die,
        stats=final_stats.to_dict(),
        save_proficiencies=list(class_def["save_proficiencies"]),
        abilities=abilities,
        hp=max_hp,
        max_hp=max_hp,
        mp=mp,
        max_mp=max_mp,
        ap=ap,
        max_ap=max_ap,
        ac=ac,
        speed=class_def["speed"],
        weapon=weapon,
        armor=armor,
        ring=ring,
        player_id=player_id or str(uuid.uuid4()),
        respawn_room=respawn_room,
        world_id=world_id,
        gold=STARTING_GOLD,
    )


def class_attack_bonus(agent: AgentState) -> int:
    """Compute attack bonus for the agent's primary weapon."""
    class_def = CLASS_DEFINITIONS[agent.agent_class]
    primary = class_def["primary_stat"]
    weapon = agent.weapon
    # finesse/ranged weapons use DEX; otherwise use class primary
    if weapon.ranged or weapon.finesse:
        stat_mod = mod(agent.stats.get("DEX", 10))
    else:
        stat_mod = mod(agent.stats.get(primary, 10))
    return stat_mod + agent.proficiency_bonus + weapon.attack_bonus_bonus


def class_damage_mod(agent: AgentState) -> int:
    """Stat-based damage modifier on the agent's primary weapon."""
    class_def = CLASS_DEFINITIONS[agent.agent_class]
    primary = class_def["primary_stat"]
    weapon = agent.weapon
    if weapon.ranged or weapon.finesse:
        stat_mod = mod(agent.stats.get("DEX", 10))
    else:
        stat_mod = mod(agent.stats.get(primary, 10))
    return stat_mod + weapon.damage_bonus + agent.ring.damage_bonus


def caster_mod(agent: AgentState) -> int:
    """Spellcasting modifier from class definition. 0 if non-caster."""
    class_def = CLASS_DEFINITIONS[agent.agent_class]
    caster_stat = class_def.get("caster_mod")
    if not caster_stat:
        return 0
    return mod(agent.stats.get(caster_stat, 10))


def spell_attack(agent: AgentState) -> int:
    return caster_mod(agent) + agent.proficiency_bonus + agent.ring.spell_attack_bonus


def spell_save_dc(agent: AgentState) -> int:
    return 8 + agent.proficiency_bonus + caster_mod(agent) + agent.ring.spell_dc_bonus


def save_throw_bonus(agent: AgentState, stat: str) -> int:
    """Bonus to a saving throw for the given stat."""
    stat_mod = mod(agent.stats.get(stat.upper(), 10))
    proficient = stat.upper() in agent.save_proficiencies
    return stat_mod + (agent.proficiency_bonus if proficient else 0) + agent.ring.save_bonus
