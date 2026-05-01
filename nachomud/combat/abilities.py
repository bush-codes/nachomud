"""Ability system — registry of all 24 abilities with resolver functions.

Phase 1 rewrite: D&D 5e-style mechanics.
- Weapon attacks: 1d20 + attack_bonus vs target AC. Nat 20 = crit (double dice).
- Spell attacks: 1d20 + spell_attack_bonus vs target AC.
- Saves: target rolls 1d20 + save_bonus vs spell_save_dc.
- Auto: no roll, applies directly.

Each ability is a function that takes (source, target_name, room, tick, agents, rooms)
and returns a list[GameEvent]. The registry dispatches by ability name.
"""
from __future__ import annotations


from nachomud.characters.character import (
    caster_mod as _caster_mod,
    class_attack_bonus,
    class_damage_mod,
    spell_attack as _spell_attack,
    spell_save_dc,
)
from nachomud.characters.effects import (
    apply_effect,
    clear_debuffs,
    is_incapacitated,
    modify_outgoing_damage,
)
from nachomud.models import AgentState, GameEvent, Item, Mob, Room, StatusEffect
from nachomud.rules.dice import roll_d20, roll_detail, roll_dice_doubled
from nachomud.rules.stats import mod as stat_mod

# ABILITY_DEFINITIONS + MULTI_WORD_ABILITIES tables appear at the bottom of this
# file — they live alongside the resolvers that consume them.


# ── Targeting helpers ──

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


def _target_failure_hint(target_name: str, room: Room, agents: list[AgentState] | None = None,
                         agent_name: str = "") -> str:
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


# ── Damage / death plumbing ──

def _mob_dies(mob: Mob, room: Room, result_parts: list[str]) -> None:
    result_parts.append(f"{mob.name} is slain!")
    if mob.loot:
        for item in mob.loot:
            room.items.append(item)
        loot_names = ", ".join(i.name for i in mob.loot)
        result_parts.append(f"Loot dropped: {loot_names}.")


def _apply_damage_to_mob(mob: Mob, damage: int, room: Room) -> tuple[int, list[str]]:
    actual = min(mob.hp, damage)
    mob.hp = max(0, mob.hp - damage)
    parts: list[str] = []
    if mob.hp <= 0:
        mob.alive = False
        _mob_dies(mob, room, parts)
    return actual, parts


def _apply_damage_to_agent(agent: AgentState, damage: int) -> list[str]:
    agent.hp = max(0, agent.hp - damage)
    parts: list[str] = []
    if agent.hp <= 0:
        agent.hp = 0
        agent.alive = False
        parts.append(f"{agent.name} has fallen!")
    return parts


# ── 5e helpers ──

def _mob_ac(mob: Mob) -> int:
    return mob.ac if mob.ac else 10


def _mob_save_bonus(mob: Mob, stat: str) -> int:
    """Mob save bonus. Uses mob.stats if defined, else 0."""
    if not mob.stats:
        return mob.proficiency_bonus // 2
    s = mob.stats.get(stat.upper(), 10)
    return stat_mod(s) + mob.proficiency_bonus  # mobs proficient in everything for v1 simplicity


def _resolve_damage_dice(spec: str, weapon: Item) -> list[str]:
    """Parse a damage spec into a list of dice notations to roll.

    'weapon'         -> [weapon.damage_die]
    'weapon+2d6'     -> [weapon.damage_die, '2d6']
    '2d6'            -> ['2d6']
    ''               -> []
    """
    if not spec:
        return []
    weapon_die = weapon.damage_die or "1d4"
    if spec == "weapon":
        return [weapon_die]
    if spec.startswith("weapon+"):
        return [weapon_die, spec[len("weapon+"):]]
    return [spec]


def _roll_damage_total(dice_list: list[str], crit: bool) -> int:
    total = 0
    for notation in dice_list:
        if crit:
            total += roll_dice_doubled(notation)
        else:
            total += roll_detail(notation).total
    return total


# ── Cost checking ──

def can_afford(source: AgentState, ability_name: str) -> tuple[bool, str]:
    defn = ABILITY_DEFINITIONS.get(ability_name)
    if not defn:
        return False, f"Unknown ability: {ability_name}"

    cost = defn["cost"]
    cost_type = defn["cost_type"]

    if cost_type == "free":
        return True, ""
    if cost_type == "mp":
        if source.mp < cost:
            return False, f"Not enough MP ({source.mp}/{cost})."
        return True, ""
    if cost_type == "ap":
        if source.ap < cost:
            return False, f"Not enough AP ({source.ap}/{cost})."
        return True, ""
    if cost_type == "hp":
        if source.hp <= cost:
            return False, f"Not enough HP to sacrifice ({source.hp} HP, costs {cost})."
        return True, ""
    return False, f"Unknown cost type: {cost_type}"


def pay_cost(source: AgentState, ability_name: str) -> None:
    defn = ABILITY_DEFINITIONS[ability_name]
    cost = defn["cost"]
    cost_type = defn["cost_type"]

    if cost_type == "mp":
        source.mp -= cost
    elif cost_type == "ap":
        source.ap -= cost
    elif cost_type == "hp":
        source.hp -= cost


# ── Attack-roll workflow ──

def _make_weapon_attack(source: AgentState, mob: Mob, dice_spec: str,
                        attack_bonus_override: int | None = None) -> tuple[bool, bool, int, int, int]:
    """Roll d20 to-hit, then damage if hit. Returns (hit, crit, d20_roll, attack_total, damage)."""
    bonus = class_attack_bonus(source) if attack_bonus_override is None else attack_bonus_override
    d20 = roll_d20()
    attack_total = d20 + bonus
    target_ac = _mob_ac(mob)

    if d20 == 1:
        return False, False, d20, attack_total, 0
    crit = d20 == 20
    hit = crit or attack_total >= target_ac
    if not hit:
        return False, False, d20, attack_total, 0

    dice_list = _resolve_damage_dice(dice_spec, source.weapon)
    raw = _roll_damage_total(dice_list, crit)
    raw += class_damage_mod(source)
    damage = modify_outgoing_damage(source, raw)
    damage = max(1, damage)
    return True, crit, d20, attack_total, damage


def _make_spell_attack(source: AgentState, mob: Mob, dice_spec: str) -> tuple[bool, bool, int, int, int]:
    """Spell attack roll. Returns (hit, crit, d20_roll, attack_total, damage)."""
    bonus = _spell_attack(source)
    d20 = roll_d20()
    attack_total = d20 + bonus
    target_ac = _mob_ac(mob)

    if d20 == 1:
        return False, False, d20, attack_total, 0
    crit = d20 == 20
    hit = crit or attack_total >= target_ac
    if not hit:
        return False, False, d20, attack_total, 0

    dice_list = _resolve_damage_dice(dice_spec, source.weapon)
    raw = _roll_damage_total(dice_list, crit)
    raw += _caster_mod(source)
    damage = modify_outgoing_damage(source, raw)
    damage = max(1, damage)
    return True, crit, d20, attack_total, damage


def _make_save(mob: Mob, stat: str, dc: int) -> tuple[bool, int, int]:
    """Mob rolls a save. Returns (succeeded, d20_roll, total)."""
    bonus = _mob_save_bonus(mob, stat)
    d20 = roll_d20()
    total = d20 + bonus
    return total >= dc, d20, total


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
    if is_incapacitated(source):
        return [GameEvent(tick, source.name, ability_name,
                          f"{source.name} is asleep and cannot act!", source.room_id)]

    affordable, err = can_afford(source, ability_name)
    if not affordable:
        return [GameEvent(tick, source.name, ability_name, err, source.room_id)]

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

    hit, crit, d20, atk_total, damage = _make_weapon_attack(source, mob, "weapon")
    if not hit:
        flavor = "critical miss" if d20 == 1 else "miss"
        result = f"{source.name} attacks {mob.name} ({d20}+{atk_total - d20}={atk_total} vs AC {_mob_ac(mob)}) — {flavor}!"
        return [GameEvent(tick, source.name, f"attack {mob.name}", result, source.room_id)]

    _, extra = _apply_damage_to_mob(mob, damage, room)
    crit_tag = " CRIT!" if crit else ""
    result = (f"{source.name} attacks {mob.name} ({d20}+{atk_total - d20}={atk_total} vs AC {_mob_ac(mob)}) — "
              f"hit{crit_tag} for {damage} damage. ({mob.name} HP: {mob.hp}/{mob.max_hp})")
    if extra:
        result += " " + " ".join(extra)
    return [GameEvent(tick, source.name, f"attack {mob.name}", result, source.room_id)]


def _resolve_cleave(source, target_name, room, tick, agents, rooms):
    pay_cost(source, "cleave")
    mobs = _living_mobs(room)
    if not mobs:
        return [GameEvent(tick, source.name, "cleave", "No enemies in this room.", source.room_id)]

    parts = []
    for mob in mobs:
        hit, crit, _d20, _atk_total, damage = _make_weapon_attack(source, mob, "weapon")
        if not hit:
            parts.append(f"{mob.name} (miss)")
            continue
        _, extra = _apply_damage_to_mob(mob, damage, room)
        crit_tag = " CRIT!" if crit else ""
        parts.append(f"{mob.name}{crit_tag} {damage} ({mob.hp}/{mob.max_hp})")
        if extra:
            parts[-1] += " " + " ".join(extra)

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
    result = f"{source.name} takes a defensive stance. Incoming damage halved this round."
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
    hit, crit, _d20, _atk_total, damage = _make_weapon_attack(source, mob, "weapon+2d8")
    if not hit:
        return [GameEvent(tick, source.name, f"smite {mob.name}",
                          f"{source.name} smites at {mob.name} — miss!", source.room_id)]
    _, extra = _apply_damage_to_mob(mob, damage, room)
    crit_tag = " CRIT!" if crit else ""
    result = f"{source.name} smites {mob.name}{crit_tag} for {damage} radiant damage. ({mob.name} HP: {mob.hp}/{mob.max_hp})"
    if extra:
        result += " " + " ".join(extra)
    return [GameEvent(tick, source.name, f"smite {mob.name}", result, source.room_id)]


def _resolve_lay_on_hands(source, target_name, room, tick, agents, rooms):
    target = source
    if target_name and target_name.lower() not in ("self", source.name.lower()):
        ally = _find_ally(agents, source, target_name)
        if not ally:
            return [GameEvent(tick, source.name, f"lay_on_hands {target_name}",
                              f"No ally named '{target_name}' here.", source.room_id)]
        target = ally
    pay_cost(source, "lay_on_hands")
    heal = max(1, int(target.max_hp * 0.40))
    target.hp = min(target.max_hp, target.hp + heal)
    result = f"{source.name} lays hands on {target.name}, restoring {heal} HP. ({target.name} HP: {target.hp}/{target.max_hp})"
    return [GameEvent(tick, source.name, f"lay_on_hands {target.name}", result, source.room_id)]


def _resolve_shield(source, target_name, room, tick, agents, rooms):
    if not target_name:
        return [GameEvent(tick, source.name, "shield", "Shield needs a target ally.", source.room_id)]
    ally = _find_ally(agents, source, target_name)
    if not ally:
        return [GameEvent(tick, source.name, f"shield {target_name}",
                          f"No ally named '{target_name}' here.", source.room_id)]
    pay_cost(source, "shield")
    apply_effect(ally, StatusEffect("shielded", source.name, -1))
    result = f"{source.name} shields {ally.name}; next attack on {ally.name} redirects to {source.name}."
    return [GameEvent(tick, source.name, f"shield {ally.name}", result, source.room_id)]


def _resolve_consecrate(source, target_name, room, tick, agents, rooms):
    pay_cost(source, "consecrate")
    mobs = _living_mobs(room)
    if not mobs:
        return [GameEvent(tick, source.name, "consecrate", "No enemies to consecrate.", source.room_id)]
    dc = spell_save_dc(source)
    parts = []
    for mob in mobs:
        saved, _d20, _ = _make_save(mob, "DEX", dc)
        dice_list = _resolve_damage_dice("3d6", source.weapon)
        raw = _roll_damage_total(dice_list, crit=False)
        damage = max(1, raw // 2 if saved else raw)
        _, extra = _apply_damage_to_mob(mob, damage, room)
        save_tag = "saved" if saved else "failed"
        parts.append(f"{mob.name} ({save_tag}) {damage} ({mob.hp}/{mob.max_hp})")
        if extra:
            parts[-1] += " " + " ".join(extra)
    result = f"{source.name} consecrates the ground (DC {dc}); " + "; ".join(parts)
    return [GameEvent(tick, source.name, "consecrate", result, source.room_id)]


def _resolve_missile(source, target_name, room, tick, agents, rooms):
    mob = _find_mob(room, target_name)
    if not mob:
        hint = _target_failure_hint(target_name, room, agents, source.name)
        return [GameEvent(tick, source.name, f"missile {target_name}", hint, source.room_id)]
    pay_cost(source, "missile")
    # Magic missile auto-hits in 5e
    dice_list = _resolve_damage_dice("1d4+1", source.weapon)
    raw = _roll_damage_total(dice_list, crit=False)
    damage = modify_outgoing_damage(source, max(1, raw))
    _, extra = _apply_damage_to_mob(mob, damage, room)
    result = f"{source.name}'s magic missile streaks at {mob.name} for {damage} force damage. ({mob.name} HP: {mob.hp}/{mob.max_hp})"
    if extra:
        result += " " + " ".join(extra)
    return [GameEvent(tick, source.name, f"missile {mob.name}", result, source.room_id)]


def _resolve_arcane_storm(source, target_name, room, tick, agents, rooms):
    pay_cost(source, "arcane_storm")
    mobs = _living_mobs(room)
    if not mobs:
        return [GameEvent(tick, source.name, "arcane_storm", "No enemies in this room.", source.room_id)]
    dc = spell_save_dc(source)
    parts = []
    for mob in mobs:
        saved, _d20, _ = _make_save(mob, "DEX", dc)
        raw = _roll_damage_total(["4d6"], crit=False)
        damage = max(1, raw // 2 if saved else raw)
        _, extra = _apply_damage_to_mob(mob, damage, room)
        save_tag = "saved" if saved else "failed"
        parts.append(f"{mob.name} ({save_tag}) {damage} ({mob.hp}/{mob.max_hp})")
        if extra:
            parts[-1] += " " + " ".join(extra)
    result = f"{source.name} unleashes an arcane storm (DC {dc}); " + "; ".join(parts)
    return [GameEvent(tick, source.name, "arcane_storm", result, source.room_id)]


def _resolve_curse(source, target_name, room, tick, agents, rooms):
    mob = _find_mob(room, target_name)
    if not mob:
        hint = _target_failure_hint(target_name, room, agents, source.name)
        return [GameEvent(tick, source.name, f"curse {target_name}", hint, source.room_id)]
    pay_cost(source, "curse")
    dc = spell_save_dc(source)
    saved, _d20, _ = _make_save(mob, "WIS", dc)
    if saved:
        result = f"{source.name} curses {mob.name} (DC {dc}) — {mob.name} resists."
    else:
        apply_effect(mob, StatusEffect("cursed", source.name, 3, value=2))
        result = f"{source.name} curses {mob.name}! (1d4 necrotic/round, 3 rounds.)"
    return [GameEvent(tick, source.name, f"curse {mob.name}", result, source.room_id)]


def _resolve_barrier(source, target_name, room, tick, agents, rooms):
    target = source
    if target_name and target_name.lower() not in ("self", source.name.lower()):
        ally = _find_ally(agents, source, target_name)
        if not ally:
            return [GameEvent(tick, source.name, f"barrier {target_name}",
                              f"No ally named '{target_name}' here.", source.room_id)]
        target = ally
    pay_cost(source, "barrier")
    apply_effect(target, StatusEffect("barrier", source.name, -1, value=8))
    result = f"{source.name} weaves a barrier around {target.name}, absorbing up to 8 damage."
    return [GameEvent(tick, source.name, f"barrier {target.name}", result, source.room_id)]


def _resolve_heal(source, target_name, room, tick, agents, rooms):
    target = source
    if target_name and target_name.lower() not in ("self", source.name.lower()):
        ally = _find_ally(agents, source, target_name)
        if not ally:
            return [GameEvent(tick, source.name, f"heal {target_name}",
                              f"No ally named '{target_name}' here.", source.room_id)]
        target = ally
    pay_cost(source, "heal")
    raw = _roll_damage_total(["2d4"], crit=False)
    heal = raw + _caster_mod(source)
    target.hp = min(target.max_hp, target.hp + heal)
    result = f"{source.name} heals {target.name} for {heal} HP. ({target.name} HP: {target.hp}/{target.max_hp})"
    return [GameEvent(tick, source.name, f"heal {target.name}", result, source.room_id)]


def _resolve_ward(source, target_name, room, tick, agents, rooms):
    target = source
    if target_name and target_name.lower() not in ("self", source.name.lower()):
        ally = _find_ally(agents, source, target_name)
        if not ally:
            return [GameEvent(tick, source.name, f"ward {target_name}",
                              f"No ally named '{target_name}' here.", source.room_id)]
        target = ally
    pay_cost(source, "ward")
    apply_effect(target, StatusEffect("warded", source.name, 3, value=3))
    result = f"{source.name} wards {target.name}; -3 incoming damage for 3 rounds."
    return [GameEvent(tick, source.name, f"ward {target.name}", result, source.room_id)]


def _resolve_holy_bolt(source, target_name, room, tick, agents, rooms):
    mob = _find_mob(room, target_name)
    if not mob:
        hint = _target_failure_hint(target_name, room, agents, source.name)
        return [GameEvent(tick, source.name, f"holy_bolt {target_name}", hint, source.room_id)]
    pay_cost(source, "holy_bolt")
    hit, crit, _d20, _atk_total, damage = _make_spell_attack(source, mob, "2d6")
    if not hit:
        return [GameEvent(tick, source.name, f"holy_bolt {mob.name}",
                          f"{source.name}'s holy bolt misses {mob.name}!", source.room_id)]
    _, extra = _apply_damage_to_mob(mob, damage, room)
    crit_tag = " CRIT!" if crit else ""
    result = f"{source.name} hurls holy radiance at {mob.name}{crit_tag} for {damage} damage. ({mob.name} HP: {mob.hp}/{mob.max_hp})"
    if extra:
        result += " " + " ".join(extra)
    return [GameEvent(tick, source.name, f"holy_bolt {mob.name}", result, source.room_id)]


def _resolve_cure(source, target_name, room, tick, agents, rooms):
    target = source
    if target_name and target_name.lower() not in ("self", source.name.lower()):
        ally = _find_ally(agents, source, target_name)
        if not ally:
            return [GameEvent(tick, source.name, f"cure {target_name}",
                              f"No ally named '{target_name}' here.", source.room_id)]
        target = ally
    pay_cost(source, "cure")
    clear_debuffs(target)
    result = f"{source.name} cures {target.name} of all debuffs."
    return [GameEvent(tick, source.name, f"cure {target.name}", result, source.room_id)]


def _resolve_aimed_shot(source, target_name, room, tick, agents, rooms):
    mob = _find_mob(room, target_name)
    if not mob:
        hint = _target_failure_hint(target_name, room, agents, source.name)
        return [GameEvent(tick, source.name, f"aimed_shot {target_name}", hint, source.room_id)]
    pay_cost(source, "aimed_shot")
    bonus = class_attack_bonus(source) + 2
    hit, crit, _d20, _atk_total, damage = _make_weapon_attack(source, mob, "weapon+1d6", attack_bonus_override=bonus)
    if not hit:
        return [GameEvent(tick, source.name, f"aimed_shot {mob.name}",
                          f"{source.name}'s aimed shot misses!", source.room_id)]
    _, extra = _apply_damage_to_mob(mob, damage, room)
    crit_tag = " CRIT!" if crit else ""
    result = f"{source.name} fires an aimed shot at {mob.name}{crit_tag} for {damage} damage. ({mob.name} HP: {mob.hp}/{mob.max_hp})"
    if extra:
        result += " " + " ".join(extra)
    return [GameEvent(tick, source.name, f"aimed_shot {mob.name}", result, source.room_id)]


def _resolve_volley(source, target_name, room, tick, agents, rooms):
    pay_cost(source, "volley")
    mobs = _living_mobs(room)
    if not mobs:
        return [GameEvent(tick, source.name, "volley", "No enemies in this room.", source.room_id)]
    parts = []
    for mob in mobs:
        hit, crit, _d20, _atk_total, damage = _make_weapon_attack(source, mob, "weapon")
        if not hit:
            parts.append(f"{mob.name} (miss)")
            continue
        _, extra = _apply_damage_to_mob(mob, damage, room)
        crit_tag = " CRIT!" if crit else ""
        parts.append(f"{mob.name}{crit_tag} {damage} ({mob.hp}/{mob.max_hp})")
        if extra:
            parts[-1] += " " + " ".join(extra)
    result = f"{source.name} looses a volley! " + "; ".join(parts)
    return [GameEvent(tick, source.name, "volley", result, source.room_id)]


def _resolve_poison_arrow(source, target_name, room, tick, agents, rooms):
    mob = _find_mob(room, target_name)
    if not mob:
        hint = _target_failure_hint(target_name, room, agents, source.name)
        return [GameEvent(tick, source.name, f"poison_arrow {target_name}", hint, source.room_id)]
    pay_cost(source, "poison_arrow")
    hit, crit, _d20, _atk_total, damage = _make_weapon_attack(source, mob, "weapon")
    if not hit:
        return [GameEvent(tick, source.name, f"poison_arrow {mob.name}",
                          f"{source.name}'s poison arrow misses!", source.room_id)]
    _, extra = _apply_damage_to_mob(mob, damage, room)
    apply_effect(mob, StatusEffect("poisoned", source.name, 3, value=2))
    crit_tag = " CRIT!" if crit else ""
    result = f"{source.name} fires a poison arrow at {mob.name}{crit_tag} for {damage} damage. Poisoned (1d4/round, 3 rounds). ({mob.name} HP: {mob.hp}/{mob.max_hp})"
    if extra:
        result += " " + " ".join(extra)
    return [GameEvent(tick, source.name, f"poison_arrow {mob.name}", result, source.room_id)]


def _resolve_sleep(source, target_name, room, tick, agents, rooms):
    mob = _find_mob(room, target_name)
    if not mob:
        hint = _target_failure_hint(target_name, room, agents, source.name)
        return [GameEvent(tick, source.name, f"sleep {target_name}", hint, source.room_id)]
    pay_cost(source, "sleep")
    dc = spell_save_dc(source)
    saved, _d20, _ = _make_save(mob, "WIS", dc)
    if saved:
        result = f"{source.name} casts sleep on {mob.name} (DC {dc}) — {mob.name} resists."
    else:
        apply_effect(mob, StatusEffect("asleep", source.name, 2))
        result = f"{source.name} casts sleep on {mob.name}; it falls unconscious for 2 rounds."
    return [GameEvent(tick, source.name, f"sleep {mob.name}", result, source.room_id)]


def _resolve_backstab(source, target_name, room, tick, agents, rooms):
    mob = _find_mob(room, target_name)
    if not mob:
        hint = _target_failure_hint(target_name, room, agents, source.name)
        return [GameEvent(tick, source.name, f"backstab {target_name}", hint, source.room_id)]
    pay_cost(source, "backstab")
    hit, crit, _d20, _atk_total, damage = _make_weapon_attack(source, mob, "weapon+2d6")
    if not hit:
        return [GameEvent(tick, source.name, f"backstab {mob.name}",
                          f"{source.name}'s backstab misses!", source.room_id)]
    _, extra = _apply_damage_to_mob(mob, damage, room)
    crit_tag = " CRIT!" if crit else ""
    result = f"{source.name} backstabs {mob.name}{crit_tag} for {damage} damage. ({mob.name} HP: {mob.hp}/{mob.max_hp})"
    if extra:
        result += " " + " ".join(extra)
    return [GameEvent(tick, source.name, f"backstab {mob.name}", result, source.room_id)]


def _resolve_bleed(source, target_name, room, tick, agents, rooms):
    mob = _find_mob(room, target_name)
    if not mob:
        hint = _target_failure_hint(target_name, room, agents, source.name)
        return [GameEvent(tick, source.name, f"bleed {target_name}", hint, source.room_id)]
    pay_cost(source, "bleed")
    hit, crit, _d20, _atk_total, damage = _make_weapon_attack(source, mob, "weapon")
    if not hit:
        return [GameEvent(tick, source.name, f"bleed {mob.name}",
                          f"{source.name}'s strike misses {mob.name}!", source.room_id)]
    _, extra = _apply_damage_to_mob(mob, damage, room)
    apply_effect(mob, StatusEffect("bleeding", source.name, 3, value=2))
    crit_tag = " CRIT!" if crit else ""
    result = f"{source.name} cuts {mob.name}{crit_tag} for {damage} damage. Bleeding (1d4/round, 3 rounds). ({mob.name} HP: {mob.hp}/{mob.max_hp})"
    if extra:
        result += " " + " ".join(extra)
    return [GameEvent(tick, source.name, f"bleed {mob.name}", result, source.room_id)]


def _resolve_evade(source, target_name, room, tick, agents, rooms):
    pay_cost(source, "evade")
    apply_effect(source, StatusEffect("evading", source.name, -1))
    result = f"{source.name} prepares to evade; next attack misses entirely."
    return [GameEvent(tick, source.name, "evade", result, source.room_id)]


def _resolve_smoke_bomb(source, target_name, room, tick, agents, rooms):
    pay_cost(source, "smoke_bomb")
    mobs = _living_mobs(room)
    for mob in mobs:
        apply_effect(mob, StatusEffect("blinded", source.name, 2, value=3))
    if mobs:
        result = f"{source.name} hurls a smoke bomb! All enemies blinded; their attacks deal -3 damage for 2 rounds."
    else:
        result = f"{source.name} hurls a smoke bomb at empty air."
    return [GameEvent(tick, source.name, "smoke_bomb", result, source.room_id)]


# ── Registry ──

ABILITY_REGISTRY = {
    "attack":       _resolve_attack,
    "cleave":       _resolve_cleave,
    "taunt":        _resolve_taunt,
    "defend":       _resolve_defend,
    "rally":        _resolve_rally,
    "smite":        _resolve_smite,
    "lay_on_hands": _resolve_lay_on_hands,
    "shield":       _resolve_shield,
    "consecrate":   _resolve_consecrate,
    "missile":      _resolve_missile,
    "arcane_storm": _resolve_arcane_storm,
    "curse":        _resolve_curse,
    "barrier":      _resolve_barrier,
    "heal":         _resolve_heal,
    "ward":         _resolve_ward,
    "holy_bolt":    _resolve_holy_bolt,
    "cure":         _resolve_cure,
    "aimed_shot":   _resolve_aimed_shot,
    "volley":       _resolve_volley,
    "poison_arrow": _resolve_poison_arrow,
    "sleep":        _resolve_sleep,
    "backstab":     _resolve_backstab,
    "bleed":        _resolve_bleed,
    "evade":        _resolve_evade,
    "smoke_bomb":   _resolve_smoke_bomb,
}

# ── Ability Definitions ────────────────────────────────────────────────
# cost_type: "mp", "ap", "hp", or "free"
# target: "enemy", "self", "ally", "ally_or_self", "all_enemies", "all_allies"
# aoe: True if ability hits all targets of that type
# damage_dice: dice notation for damage (or empty if non-damaging)
# damage_type: "physical" (uses weapon mod), "radiant", "fire", "necrotic", etc.
# attack_type: "weapon" (d20+attack_bonus vs AC), "spell_attack" (d20+spell_attack vs AC),
#              "save" (target rolls vs DC), "auto" (no roll, auto-applies)
# save_stat: which save the target rolls (if attack_type=="save")

ABILITY_DEFINITIONS = {
    # ── Warrior (AP-based) ──
    "attack":       {"cost": 0, "cost_type": "free", "target": "enemy", "aoe": False,
                     "attack_type": "weapon", "damage_dice": "weapon",
                     "description": "Melee weapon attack."},
    "cleave":       {"cost": 3, "cost_type": "ap", "target": "all_enemies", "aoe": True,
                     "attack_type": "weapon", "damage_dice": "weapon",
                     "description": "Sweeping attack against all enemies (3 AP)."},
    "taunt":        {"cost": 2, "cost_type": "ap", "target": "self", "aoe": False,
                     "attack_type": "auto", "damage_dice": "",
                     "description": "Force all mobs to target you next turn (2 AP)."},
    "defend":       {"cost": 2, "cost_type": "ap", "target": "self", "aoe": False,
                     "attack_type": "auto", "damage_dice": "",
                     "description": "Halve incoming damage this round (2 AP)."},
    "rally":        {"cost": 4, "cost_type": "ap", "target": "all_allies", "aoe": True,
                     "attack_type": "auto", "damage_dice": "",
                     "description": "Allies deal +2 damage on next hit (4 AP)."},

    # ── Paladin (MP-based, CHA caster) ──
    "smite":        {"cost": 2, "cost_type": "mp", "target": "enemy", "aoe": False,
                     "attack_type": "weapon", "damage_dice": "weapon+2d8",
                     "damage_type": "radiant",
                     "description": "Strike with radiant fury (weapon + 2d8 radiant, 2 MP)."},
    "lay_on_hands": {"cost": 3, "cost_type": "mp", "target": "ally_or_self", "aoe": False,
                     "attack_type": "auto", "damage_dice": "",
                     "description": "Restore 40% of target's max HP (3 MP)."},
    "shield":       {"cost": 2, "cost_type": "mp", "target": "ally", "aoe": False,
                     "attack_type": "auto", "damage_dice": "",
                     "description": "Redirect next attack on ally to you (2 MP)."},
    "consecrate":   {"cost": 4, "cost_type": "mp", "target": "all_enemies", "aoe": True,
                     "attack_type": "save", "save_stat": "DEX", "damage_dice": "3d6",
                     "damage_type": "radiant",
                     "description": "Holy AoE; DEX save halves (3d6 radiant, 4 MP)."},

    # ── Mage (MP-based, INT caster) ──
    "missile":      {"cost": 1, "cost_type": "mp", "target": "enemy", "aoe": False,
                     "attack_type": "auto", "damage_dice": "1d4+1",
                     "damage_type": "force",
                     "description": "Magic missile (auto-hit, 1d4+1 force, 1 MP)."},
    "arcane_storm": {"cost": 4, "cost_type": "mp", "target": "all_enemies", "aoe": True,
                     "attack_type": "save", "save_stat": "DEX", "damage_dice": "4d6",
                     "damage_type": "lightning",
                     "description": "Lightning AoE; DEX save halves (4d6, 4 MP)."},
    "curse":        {"cost": 2, "cost_type": "mp", "target": "enemy", "aoe": False,
                     "attack_type": "save", "save_stat": "WIS", "damage_dice": "",
                     "description": "WIS save or take 1d4 necrotic damage per round for 3 rounds (2 MP)."},
    "barrier":      {"cost": 3, "cost_type": "mp", "target": "ally_or_self", "aoe": False,
                     "attack_type": "auto", "damage_dice": "",
                     "description": "Absorb up to 8 damage on target (3 MP)."},

    # ── Cleric (MP-based, WIS caster) ──
    "heal":         {"cost": 2, "cost_type": "mp", "target": "ally_or_self", "aoe": False,
                     "attack_type": "auto", "damage_dice": "2d4",
                     "description": "Restore 2d4 + WIS_mod HP (2 MP)."},
    "ward":         {"cost": 2, "cost_type": "mp", "target": "ally_or_self", "aoe": False,
                     "attack_type": "auto", "damage_dice": "",
                     "description": "Reduce target's incoming damage by 3 for 3 rounds (2 MP)."},
    "holy_bolt":    {"cost": 2, "cost_type": "mp", "target": "enemy", "aoe": False,
                     "attack_type": "spell_attack", "damage_dice": "2d6",
                     "damage_type": "radiant",
                     "description": "Radiant bolt; spell attack (2d6 radiant, 2 MP)."},
    "cure":         {"cost": 1, "cost_type": "mp", "target": "ally_or_self", "aoe": False,
                     "attack_type": "auto", "damage_dice": "",
                     "description": "Remove all debuffs from target (1 MP)."},

    # ── Ranger (MP-based, WIS caster) ──
    "aimed_shot":   {"cost": 3, "cost_type": "mp", "target": "enemy", "aoe": False,
                     "attack_type": "weapon", "damage_dice": "weapon+1d6",
                     "description": "Aimed strike (weapon + 1d6, +2 attack bonus, 3 MP)."},
    "volley":       {"cost": 3, "cost_type": "mp", "target": "all_enemies", "aoe": True,
                     "attack_type": "weapon", "damage_dice": "weapon",
                     "description": "Volley of arrows; one weapon attack per enemy (3 MP)."},
    "poison_arrow": {"cost": 2, "cost_type": "mp", "target": "enemy", "aoe": False,
                     "attack_type": "weapon", "damage_dice": "weapon",
                     "description": "Weapon attack + 1d4 poison/round for 3 rounds on hit (2 MP)."},
    "sleep":        {"cost": 3, "cost_type": "mp", "target": "enemy", "aoe": False,
                     "attack_type": "save", "save_stat": "WIS", "damage_dice": "",
                     "description": "WIS save or fall asleep for 2 rounds (3 MP)."},

    # ── Rogue (mixed HP/MP) ──
    "backstab":     {"cost": 3, "cost_type": "hp", "target": "enemy", "aoe": False,
                     "attack_type": "weapon", "damage_dice": "weapon+2d6",
                     "description": "Sneak attack (weapon + 2d6, costs 3 HP)."},
    "bleed":        {"cost": 2, "cost_type": "mp", "target": "enemy", "aoe": False,
                     "attack_type": "weapon", "damage_dice": "weapon",
                     "description": "Weapon attack + bleed 1d4/round for 3 rounds (2 MP)."},
    "evade":        {"cost": 2, "cost_type": "hp", "target": "self", "aoe": False,
                     "attack_type": "auto", "damage_dice": "",
                     "description": "Negate next incoming attack (costs 2 HP)."},
    "smoke_bomb":   {"cost": 3, "cost_type": "mp", "target": "all_enemies", "aoe": True,
                     "attack_type": "auto", "damage_dice": "",
                     "description": "Enemies deal -3 damage for 2 rounds (3 MP)."},
}

MULTI_WORD_ABILITIES = {
    "lay on hands": "lay_on_hands",
    "aimed shot": "aimed_shot",
    "poison arrow": "poison_arrow",
    "arcane storm": "arcane_storm",
    "holy bolt": "holy_bolt",
    "smoke bomb": "smoke_bomb",
}
