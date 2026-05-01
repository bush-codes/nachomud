"""Tests for abilities.py — all 24 abilities under the 5e rewrite.

Asserts structural properties (event emitted, status applied, HP changed within
expected bounds) rather than exact damage numbers, so changes to dice or
balancing don't cascade. Dice RNG is seeded by the autouse fixture.
"""
from __future__ import annotations

import nachomud.rules.dice as dice
from nachomud.combat.abilities import can_afford, pay_cost, resolve_ability
from nachomud.characters.character import create_character
from nachomud.characters.effects import has_effect, get_effect
from nachomud.models import AgentState, Item, Mob, Room
from nachomud.rules.stats import Stats


# ── Helpers ──

def _make_warrior(hp_full=True, ap=10) -> AgentState:
    a = create_character("Kael", "Human", "Warrior",
                         Stats(STR=15, DEX=12, CON=14, INT=8, WIS=10, CHA=13))
    a.room_id = "room_1"
    a.abilities = ["attack", "cleave", "taunt", "defend", "rally"]
    if not hp_full:
        a.hp = 1
    a.ap = ap
    return a


def _make_paladin() -> AgentState:
    a = create_character("Aldric", "Human", "Paladin",
                         Stats(STR=15, DEX=10, CON=13, INT=8, WIS=12, CHA=14))
    a.room_id = "room_1"
    a.abilities = ["attack", "smite", "lay_on_hands", "shield", "consecrate"]
    return a


def _make_mage() -> AgentState:
    a = create_character("Lyria", "Human", "Mage",
                         Stats(STR=8, DEX=14, CON=12, INT=15, WIS=13, CHA=10))
    a.room_id = "room_1"
    a.abilities = ["attack", "missile", "arcane_storm", "curse", "barrier"]
    return a


def _make_cleric() -> AgentState:
    a = create_character("Sera", "Human", "Cleric",
                         Stats(STR=10, DEX=12, CON=14, INT=8, WIS=15, CHA=13))
    a.room_id = "room_1"
    a.abilities = ["attack", "heal", "ward", "holy_bolt", "cure"]
    return a


def _make_ranger() -> AgentState:
    a = create_character("Finn", "Human", "Ranger",
                         Stats(STR=12, DEX=15, CON=13, INT=8, WIS=14, CHA=10))
    a.room_id = "room_1"
    a.abilities = ["attack", "aimed_shot", "volley", "poison_arrow", "sleep"]
    return a


def _make_rogue() -> AgentState:
    a = create_character("Shade", "Human", "Rogue",
                         Stats(STR=8, DEX=15, CON=14, INT=13, WIS=10, CHA=12))
    a.room_id = "room_1"
    a.abilities = ["attack", "backstab", "bleed", "evade", "smoke_bomb"]
    return a


def _make_mob(name="Goblin", hp=20, ac=11) -> Mob:
    return Mob(name=name, hp=hp, max_hp=hp, atk=2, ac=ac, level=1,
               stats={"STR": 8, "DEX": 14, "CON": 10, "INT": 8, "WIS": 8, "CHA": 6},
               damage_die="1d4", damage_bonus=2,
               faction="goblin_clan")


def _room(*mobs: Mob) -> Room:
    return Room(id="room_1", name="Arena", mobs=list(mobs))


def _rooms(room: Room) -> dict[str, Room]:
    return {"room_1": room}


def _seed_for_hit():
    """Re-seed so the next d20 is high (force a hit)."""
    # Find a seed whose first d20 is >=15. We'll just use 1.
    dice.seed(1)


def _seed_for_miss():
    """Seed so the next d20 is low (force a miss)."""
    # We need a seed whose first roll is low.
    dice.seed(7)


# ── Cost system ──

def test_cost_attack_is_free():
    a = _make_warrior()
    ok, _ = can_afford(a, "attack")
    assert ok


def test_cost_cleave_requires_ap():
    a = _make_warrior(ap=2)
    ok, msg = can_afford(a, "cleave")
    assert not ok
    assert "AP" in msg


def test_cost_smite_requires_mp():
    a = _make_paladin()
    a.mp = 1
    ok, msg = can_afford(a, "smite")
    assert not ok
    assert "MP" in msg


def test_cost_backstab_requires_hp():
    a = _make_rogue()
    a.hp = 2
    ok, msg = can_afford(a, "backstab")
    assert not ok
    assert "HP" in msg


def test_pay_mp_deducts():
    a = _make_paladin()
    before = a.mp
    pay_cost(a, "smite")
    assert a.mp == before - 2


# ── Attack-roll mechanics ──

def test_attack_returns_event():
    a = _make_warrior()
    mob = _make_mob()
    room = _room(mob)
    events = resolve_ability(a, "attack", "Goblin", room, 1, [a], _rooms(room))
    assert len(events) == 1
    assert events[0].action == "attack Goblin"


def test_attack_target_not_found():
    a = _make_warrior()
    room = _room()
    events = resolve_ability(a, "attack", "Dragon", room, 1, [a], _rooms(room))
    assert "No enemy" in events[0].result or "no enem" in events[0].result.lower()


def test_attack_at_high_to_hit_damages_mob():
    """Force a hit by giving the warrior absurd attack bonus and the mob low AC."""
    a = _make_warrior()
    mob = _make_mob(ac=5)  # easy to hit
    room = _room(mob)
    starting_hp = mob.hp
    # Loop a few times because RNG can still produce a nat-1 miss
    hits = 0
    for _ in range(10):
        events = resolve_ability(a, "attack", "Goblin", room, 1, [a], _rooms(room))
        if mob.hp < starting_hp:
            hits += 1
            break
        # Reset HP and try again
        mob.hp = starting_hp
    assert hits > 0, "Expected at least one hit on AC 5 mob in 10 attempts"


def test_attack_against_high_ac_mostly_misses():
    a = _make_warrior()
    mob = _make_mob(ac=30)  # impossible to hit (only nat 20)
    room = _room(mob)
    misses = 0
    for _ in range(20):
        starting = mob.hp
        resolve_ability(a, "attack", "Goblin", room, 1, [a], _rooms(room))
        if mob.hp == starting:
            misses += 1
        else:
            mob.hp = starting  # reset for next iteration
    # Statistically should be 19/20 misses
    assert misses >= 18


def test_attack_kills_low_hp_mob():
    a = _make_warrior()
    mob = _make_mob(hp=1, ac=5)
    room = _room(mob)
    for _ in range(10):
        if not mob.alive:
            break
        events = resolve_ability(a, "attack", "Goblin", room, 1, [a], _rooms(room))
    assert not mob.alive
    assert mob.hp == 0


# ── AoE / status effects ──

def test_cleave_hits_all_living_mobs():
    a = _make_warrior()
    m1 = _make_mob("Goblin A", ac=5)
    m2 = _make_mob("Goblin B", ac=5)
    room = _room(m1, m2)
    events = resolve_ability(a, "cleave", "", room, 1, [a], _rooms(room))
    assert events[0].action == "cleave"
    # at least one mob took damage
    assert m1.hp < m1.max_hp or m2.hp < m2.max_hp


def test_taunt_applies_status():
    a = _make_warrior()
    mob = _make_mob()
    room = _room(mob)
    resolve_ability(a, "taunt", "", room, 1, [a], _rooms(room))
    assert has_effect(mob, "taunted")


def test_defend_applies_self_status():
    a = _make_warrior()
    room = _room()
    resolve_ability(a, "defend", "", room, 1, [a], _rooms(room))
    assert has_effect(a, "defending")


def test_rally_buffs_allies():
    a = _make_warrior()
    ally = _make_paladin()
    ally.room_id = "room_1"
    room = _room()
    resolve_ability(a, "rally", "", room, 1, [a, ally], _rooms(room))
    assert has_effect(ally, "rallied")


# ── Paladin abilities ──

def test_smite_consumes_mp():
    a = _make_paladin()
    mob = _make_mob(ac=5)
    room = _room(mob)
    before_mp = a.mp
    resolve_ability(a, "smite", "Goblin", room, 1, [a], _rooms(room))
    assert a.mp == before_mp - 2


def test_lay_on_hands_self_heals():
    a = _make_paladin()
    a.hp = 5
    room = _room()
    resolve_ability(a, "lay_on_hands", "", room, 1, [a], _rooms(room))
    assert a.hp > 5


def test_lay_on_hands_ally():
    a = _make_paladin()
    ally = _make_mage()
    ally.hp = 1
    room = _room()
    resolve_ability(a, "lay_on_hands", "Lyria", room, 1, [a, ally], _rooms(room))
    assert ally.hp > 1


def test_shield_redirects_to_paladin():
    a = _make_paladin()
    ally = _make_mage()
    room = _room()
    resolve_ability(a, "shield", "Lyria", room, 1, [a, ally], _rooms(room))
    assert has_effect(ally, "shielded")


def test_consecrate_aoe_save():
    a = _make_paladin()
    m1 = _make_mob("Goblin A")
    m2 = _make_mob("Goblin B")
    room = _room(m1, m2)
    events = resolve_ability(a, "consecrate", "", room, 1, [a], _rooms(room))
    # Both mobs took some damage (auto-roll, save halves)
    assert m1.hp < m1.max_hp
    assert m2.hp < m2.max_hp
    assert events[0].action == "consecrate"


# ── Mage abilities ──

def test_missile_auto_hits():
    a = _make_mage()
    mob = _make_mob(ac=99)  # auto-hit ignores AC
    room = _room(mob)
    resolve_ability(a, "missile", "Goblin", room, 1, [a], _rooms(room))
    assert mob.hp < mob.max_hp


def test_arcane_storm_aoe():
    a = _make_mage()
    m1 = _make_mob("Goblin A")
    m2 = _make_mob("Goblin B")
    room = _room(m1, m2)
    resolve_ability(a, "arcane_storm", "", room, 1, [a], _rooms(room))
    assert m1.hp < m1.max_hp
    assert m2.hp < m2.max_hp


def test_curse_save_or_apply():
    a = _make_mage()
    mob = _make_mob()
    room = _room(mob)
    # Loop to ensure at least one fail (mob's WIS is low)
    found = False
    for _ in range(20):
        resolve_ability(a, "curse", "Goblin", room, 1, [a], _rooms(room))
        if has_effect(mob, "cursed"):
            found = True
            break
        a.mp = 25  # refill
    assert found, "Expected curse to land at least once in 20 attempts"


def test_barrier_applies_absorb():
    a = _make_mage()
    room = _room()
    resolve_ability(a, "barrier", "", room, 1, [a], _rooms(room))
    e = get_effect(a, "barrier")
    assert e is not None and e.value == 8


# ── Cleric abilities ──

def test_heal_self_restores_hp():
    a = _make_cleric()
    a.hp = 1
    room = _room()
    resolve_ability(a, "heal", "", room, 1, [a], _rooms(room))
    assert a.hp > 1


def test_heal_caps_at_max_hp():
    a = _make_cleric()
    room = _room()
    resolve_ability(a, "heal", "", room, 1, [a], _rooms(room))
    assert a.hp == a.max_hp


def test_holy_bolt_spell_attack():
    a = _make_cleric()
    mob = _make_mob(ac=5)
    room = _room(mob)
    for _ in range(10):
        if mob.hp < mob.max_hp:
            break
        resolve_ability(a, "holy_bolt", "Goblin", room, 1, [a], _rooms(room))
        a.mp = 18
    assert mob.hp < mob.max_hp


def test_ward_applies_status():
    a = _make_cleric()
    ally = _make_mage()
    room = _room()
    resolve_ability(a, "ward", "Lyria", room, 1, [a, ally], _rooms(room))
    assert has_effect(ally, "warded")


def test_cure_clears_debuffs():
    a = _make_cleric()
    ally = _make_mage()
    from nachomud.models import StatusEffect
    from nachomud.characters.effects import apply_effect
    apply_effect(ally, StatusEffect("poisoned", "X", 3, value=2))
    apply_effect(ally, StatusEffect("cursed", "X", 3, value=2))
    room = _room()
    resolve_ability(a, "cure", "Lyria", room, 1, [a, ally], _rooms(room))
    assert not has_effect(ally, "poisoned")
    assert not has_effect(ally, "cursed")


# ── Ranger abilities ──

def test_aimed_shot_attack_bonus():
    a = _make_ranger()
    mob = _make_mob(ac=5)
    room = _room(mob)
    # Should reliably hit AC 5 with bonus
    for _ in range(10):
        if mob.hp < mob.max_hp:
            break
        resolve_ability(a, "aimed_shot", "Goblin", room, 1, [a], _rooms(room))
        a.mp = 10
    assert mob.hp < mob.max_hp


def test_volley_aoe():
    a = _make_ranger()
    m1 = _make_mob("Goblin A", ac=5)
    m2 = _make_mob("Goblin B", ac=5)
    room = _room(m1, m2)
    resolve_ability(a, "volley", "", room, 1, [a], _rooms(room))
    # Most likely both took damage
    assert (m1.hp < m1.max_hp) or (m2.hp < m2.max_hp)


def test_poison_arrow_applies_dot_on_hit():
    a = _make_ranger()
    mob = _make_mob(ac=5)
    room = _room(mob)
    # Force a hit
    for _ in range(10):
        if has_effect(mob, "poisoned"):
            break
        resolve_ability(a, "poison_arrow", "Goblin", room, 1, [a], _rooms(room))
        a.mp = 10
        mob.hp = mob.max_hp
    assert has_effect(mob, "poisoned")


def test_sleep_save_or_status():
    a = _make_ranger()
    mob = _make_mob()
    room = _room(mob)
    found = False
    for _ in range(20):
        resolve_ability(a, "sleep", "Goblin", room, 1, [a], _rooms(room))
        if has_effect(mob, "asleep"):
            found = True
            break
        a.mp = 10
    assert found


# ── Rogue abilities ──

def test_backstab_costs_hp():
    a = _make_rogue()
    mob = _make_mob(ac=5)
    room = _room(mob)
    before_hp = a.hp
    resolve_ability(a, "backstab", "Goblin", room, 1, [a], _rooms(room))
    assert a.hp == before_hp - 3


def test_bleed_applies_dot_on_hit():
    a = _make_rogue()
    mob = _make_mob(ac=5)
    room = _room(mob)
    for _ in range(10):
        if has_effect(mob, "bleeding"):
            break
        resolve_ability(a, "bleed", "Goblin", room, 1, [a], _rooms(room))
        a.mp = 8
        mob.hp = mob.max_hp
    assert has_effect(mob, "bleeding")


def test_evade_self_status():
    a = _make_rogue()
    room = _room()
    resolve_ability(a, "evade", "", room, 1, [a], _rooms(room))
    assert has_effect(a, "evading")


def test_smoke_bomb_blinds_mobs():
    a = _make_rogue()
    mob = _make_mob()
    room = _room(mob)
    resolve_ability(a, "smoke_bomb", "", room, 1, [a], _rooms(room))
    assert has_effect(mob, "blinded")
