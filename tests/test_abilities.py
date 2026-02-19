"""Tests for abilities.py — all 24 abilities."""
from __future__ import annotations

import math

from abilities import resolve_ability, can_afford, pay_cost
from effects import has_effect, get_effect
from models import AgentState, Item, Mob, Room, StatusEffect


def _make_warrior(hp=25, ap=10) -> AgentState:
    a = AgentState(
        name="Kael", personality="", agent_class="Warrior",
        hp=hp, max_hp=25, mp=0, max_mp=0,
        weapon=Item("Longsword", "weapon", atk=5),
        armor=Item("Chainmail", "armor", pdef=3),
        ring=Item("Iron Band", "ring", mdmg=1, mdef=1),
        room_id="room_1", ap=ap, max_ap=10, speed=3,
    )
    return a


def _make_paladin(hp=20, mp=8) -> AgentState:
    return AgentState(
        name="Aldric", personality="", agent_class="Paladin",
        hp=hp, max_hp=20, mp=mp, max_mp=8,
        weapon=Item("Warhammer", "weapon", atk=4),
        armor=Item("Plate", "armor", pdef=4, mdef=1),
        ring=Item("Holy Signet", "ring", mdmg=2, mdef=2),
        room_id="room_1", speed=3,
    )


def _make_mage(hp=8, mp=25) -> AgentState:
    return AgentState(
        name="Lyria", personality="", agent_class="Mage",
        hp=hp, max_hp=8, mp=mp, max_mp=25,
        weapon=Item("Staff", "weapon", atk=2),
        armor=Item("Robes", "armor", pdef=1, mdef=3),
        ring=Item("Focus", "ring", mdmg=5, mdef=2),
        room_id="room_1", speed=4,
    )


def _make_cleric(hp=14, mp=18) -> AgentState:
    return AgentState(
        name="Sera", personality="", agent_class="Cleric",
        hp=hp, max_hp=14, mp=mp, max_mp=18,
        weapon=Item("Mace", "weapon", atk=3),
        armor=Item("Vestments", "armor", pdef=2, mdef=2),
        ring=Item("Beads", "ring", mdmg=4, mdef=2),
        room_id="room_1", speed=3,
    )


def _make_ranger(hp=14, mp=10) -> AgentState:
    return AgentState(
        name="Finn", personality="", agent_class="Ranger",
        hp=hp, max_hp=14, mp=mp, max_mp=10,
        weapon=Item("Bow", "weapon", atk=4),
        armor=Item("Leather", "armor", pdef=2, mdef=1),
        ring=Item("Charm", "ring", mdmg=3, mdef=1),
        room_id="room_1", speed=5,
    )


def _make_rogue(hp=12, mp=8) -> AgentState:
    return AgentState(
        name="Shade", personality="", agent_class="Rogue",
        hp=hp, max_hp=12, mp=mp, max_mp=8,
        weapon=Item("Daggers", "weapon", atk=4),
        armor=Item("Cloak", "armor", pdef=1, mdef=1),
        ring=Item("Venom Ring", "ring", mdmg=2, mdef=1),
        room_id="room_1", speed=6,
    )


def _make_mob(name="Goblin", hp=10, atk=3, pdef=0, mdef=0) -> Mob:
    return Mob(name=name, hp=hp, max_hp=hp, atk=atk, pdef=pdef, mdef=mdef)


def _make_room(*mobs, room_id="room_1") -> Room:
    return Room(id=room_id, name="Test Room", mobs=list(mobs))


def _rooms(room) -> dict[str, Room]:
    return {room.id: room}


# ── Attack ──

def test_attack_basic():
    w = _make_warrior()
    mob = _make_mob(hp=20)
    room = _make_room(mob)
    events = resolve_ability(w, "attack", "Goblin", room, 1, [w], _rooms(room))
    assert "attacks" in events[0].result
    assert mob.hp == 20 - 5  # atk=5, mob pdef=0


def test_attack_invalid_target():
    w = _make_warrior()
    room = _make_room()
    events = resolve_ability(w, "attack", "Dragon", room, 1, [w], _rooms(room))
    assert "No enemy" in events[0].result or "No enemies" in events[0].result


# ── Cleave (Warrior) ──

def test_cleave_aoe():
    w = _make_warrior(ap=10)
    mob1 = _make_mob("Gob A", hp=10)
    mob2 = _make_mob("Gob B", hp=10)
    room = _make_room(mob1, mob2)
    events = resolve_ability(w, "cleave", "", room, 1, [w], _rooms(room))
    assert "cleaves" in events[0].result
    assert mob1.hp < 10
    assert mob2.hp < 10
    assert w.ap == 7  # cost 3


def test_cleave_no_ap():
    w = _make_warrior(ap=0)
    room = _make_room(_make_mob())
    events = resolve_ability(w, "cleave", "", room, 1, [w], _rooms(room))
    assert "Not enough AP" in events[0].result


# ── Taunt (Warrior) ──

def test_taunt():
    w = _make_warrior(ap=10)
    mob = _make_mob()
    room = _make_room(mob)
    events = resolve_ability(w, "taunt", "", room, 1, [w], _rooms(room))
    assert "taunts" in events[0].result
    assert has_effect(mob, "taunted")
    assert w.ap == 8


# ── Defend (Warrior) ──

def test_defend():
    w = _make_warrior(ap=10)
    room = _make_room()
    events = resolve_ability(w, "defend", "", room, 1, [w], _rooms(room))
    assert "defensive" in events[0].result
    assert has_effect(w, "defending")


# ── Rally (Warrior) ──

def test_rally():
    w = _make_warrior(ap=10)
    mage = _make_mage()
    room = _make_room()
    events = resolve_ability(w, "rally", "", room, 1, [w, mage], _rooms(room))
    assert "rallies" in events[0].result
    assert has_effect(mage, "rallied")
    assert not has_effect(w, "rallied")  # doesn't rally self


# ── Smite (Paladin) ──

def test_smite():
    p = _make_paladin()
    mob = _make_mob(hp=20, mdef=1)
    room = _make_room(mob)
    events = resolve_ability(p, "smite", "Goblin", room, 1, [p], _rooms(room))
    assert "smites" in events[0].result
    # floor(4 * 1.5) = 6, - 1 mdef = 5 damage
    assert mob.hp == 15
    assert p.mp == 6  # cost 2


# ── Lay on Hands (Paladin) ──

def test_lay_on_hands_self():
    p = _make_paladin(hp=10)
    room = _make_room()
    events = resolve_ability(p, "lay_on_hands", "", room, 1, [p], _rooms(room))
    assert "lays on hands" in events[0].result
    # ceil(20 * 0.40) = 8
    assert p.hp == 18
    assert p.mp == 5


def test_lay_on_hands_ally():
    p = _make_paladin()
    mage = _make_mage(hp=3)
    room = _make_room()
    events = resolve_ability(p, "lay_on_hands", "Lyria", room, 1, [p, mage], _rooms(room))
    assert "Lyria" in events[0].result
    # ceil(8 * 0.40) = 4 → hp 3+4=7
    assert mage.hp == 7


# ── Shield (Paladin) ──

def test_shield():
    p = _make_paladin()
    mage = _make_mage()
    room = _make_room()
    events = resolve_ability(p, "shield", "Lyria", room, 1, [p, mage], _rooms(room))
    assert "shields" in events[0].result
    assert has_effect(mage, "shielded")


# ── Consecrate (Paladin) ──

def test_consecrate():
    p = _make_paladin()
    mob1 = _make_mob("A", hp=10, mdef=1)
    mob2 = _make_mob("B", hp=10, mdef=0)
    room = _make_room(mob1, mob2)
    events = resolve_ability(p, "consecrate", "", room, 1, [p], _rooms(room))
    assert "consecrates" in events[0].result
    assert mob1.hp < 10
    assert mob2.hp < 10


# ── Missile (Mage) ──

def test_missile():
    m = _make_mage()
    mob = _make_mob(hp=10, mdef=1)
    room = _make_room(mob)
    events = resolve_ability(m, "missile", "Goblin", room, 1, [m], _rooms(room))
    assert "missile" in events[0].result
    # mdmg=5, - 1 mdef = 4 damage
    assert mob.hp == 6
    assert m.mp == 24


# ── Arcane Storm (Mage) ──

def test_arcane_storm():
    m = _make_mage()
    mob1 = _make_mob("A", hp=15)
    mob2 = _make_mob("B", hp=15)
    room = _make_room(mob1, mob2)
    events = resolve_ability(m, "arcane_storm", "", room, 1, [m], _rooms(room))
    assert "arcane storm" in events[0].result
    # mdmg*2=10 per mob
    assert mob1.hp == 5
    assert mob2.hp == 5
    assert m.mp == 21  # cost 4


# ── Curse (Mage) ──

def test_curse():
    m = _make_mage()
    mob = _make_mob()
    room = _make_room(mob)
    events = resolve_ability(m, "curse", "Goblin", room, 1, [m], _rooms(room))
    assert "curses" in events[0].result
    assert has_effect(mob, "cursed")
    eff = get_effect(mob, "cursed")
    assert eff.value == 2
    assert eff.remaining_ticks == 3


# ── Barrier (Mage) ──

def test_barrier():
    m = _make_mage()
    w = _make_warrior()
    room = _make_room()
    events = resolve_ability(m, "barrier", "Kael", room, 1, [m, w], _rooms(room))
    assert "barrier" in events[0].result
    assert has_effect(w, "barrier")
    assert get_effect(w, "barrier").value == 8


# ── Heal (Cleric) ──

def test_heal_self():
    c = _make_cleric(hp=5)
    room = _make_room()
    events = resolve_ability(c, "heal", "", room, 1, [c], _rooms(room))
    assert "heals" in events[0].result
    # ceil(14 * 0.30) = 5 → 5+5=10
    assert c.hp == 10


def test_heal_ally():
    c = _make_cleric()
    w = _make_warrior(hp=10)
    room = _make_room()
    events = resolve_ability(c, "heal", "Kael", room, 1, [c, w], _rooms(room))
    # ceil(25 * 0.30) = 8 → 10+8=18
    assert w.hp == 18


# ── Ward (Cleric) ──

def test_ward():
    c = _make_cleric()
    w = _make_warrior()
    room = _make_room()
    events = resolve_ability(c, "ward", "Kael", room, 1, [c, w], _rooms(room))
    assert "wards" in events[0].result
    assert has_effect(w, "warded")


# ── Holy Bolt (Cleric) ──

def test_holy_bolt():
    c = _make_cleric()
    mob = _make_mob(hp=20, mdef=1)
    room = _make_room(mob)
    events = resolve_ability(c, "holy_bolt", "Goblin", room, 1, [c], _rooms(room))
    assert "holy bolt" in events[0].result
    # floor(4 * 1.5) = 6, - 1 mdef = 5
    assert mob.hp == 15


# ── Cure (Cleric) ──

def test_cure():
    c = _make_cleric()
    w = _make_warrior()
    from effects import apply_effect
    apply_effect(w, StatusEffect("poisoned", "enemy", 3, value=2))
    apply_effect(w, StatusEffect("cursed", "enemy", 3, value=2))
    room = _make_room()
    events = resolve_ability(c, "cure", "Kael", room, 1, [c, w], _rooms(room))
    assert "cures" in events[0].result
    assert not has_effect(w, "poisoned")
    assert not has_effect(w, "cursed")


# ── Aimed Shot (Ranger) ──

def test_aimed_shot():
    r = _make_ranger()
    mob = _make_mob(hp=20, pdef=2)
    room = _make_room(mob)
    events = resolve_ability(r, "aimed_shot", "Goblin", room, 1, [r], _rooms(room))
    assert "aimed shot" in events[0].result
    # atk*2=8, - 2 pdef = 6
    assert mob.hp == 14
    assert r.mp == 7  # cost 3


# ── Volley (Ranger) ──

def test_volley():
    r = _make_ranger()
    mob1 = _make_mob("A", hp=10)
    mob2 = _make_mob("B", hp=10)
    room = _make_room(mob1, mob2)
    events = resolve_ability(r, "volley", "", room, 1, [r], _rooms(room))
    assert "volley" in events[0].result
    assert mob1.hp < 10
    assert mob2.hp < 10


# ── Poison Arrow (Ranger) ──

def test_poison_arrow():
    r = _make_ranger()
    mob = _make_mob()
    room = _make_room(mob)
    events = resolve_ability(r, "poison_arrow", "Goblin", room, 1, [r], _rooms(room))
    assert "poison arrow" in events[0].result
    assert has_effect(mob, "poisoned")


# ── Sleep (Ranger) ──

def test_sleep():
    r = _make_ranger()
    mob = _make_mob()
    room = _make_room(mob)
    events = resolve_ability(r, "sleep", "Goblin", room, 1, [r], _rooms(room))
    assert "sleep" in events[0].result
    assert has_effect(mob, "asleep")


# ── Backstab (Rogue, HP cost) ──

def test_backstab():
    rogue = _make_rogue()
    mob = _make_mob(hp=20, pdef=5)
    room = _make_room(mob)
    events = resolve_ability(rogue, "backstab", "Goblin", room, 1, [rogue], _rooms(room))
    assert "backstabs" in events[0].result
    # floor(4 * 2.5) = 10, ignores defense
    assert mob.hp == 10
    assert rogue.hp == 9  # cost 3 HP


def test_backstab_too_low_hp():
    rogue = _make_rogue(hp=3)
    mob = _make_mob()
    room = _make_room(mob)
    events = resolve_ability(rogue, "backstab", "Goblin", room, 1, [rogue], _rooms(room))
    assert "Not enough HP" in events[0].result


# ── Bleed (Rogue) ──

def test_bleed():
    rogue = _make_rogue()
    mob = _make_mob()
    room = _make_room(mob)
    events = resolve_ability(rogue, "bleed", "Goblin", room, 1, [rogue], _rooms(room))
    assert "bleed" in events[0].result
    assert has_effect(mob, "bleeding")


# ── Evade (Rogue, HP cost) ──

def test_evade():
    rogue = _make_rogue()
    room = _make_room()
    events = resolve_ability(rogue, "evade", "", room, 1, [rogue], _rooms(room))
    assert "evade" in events[0].result
    assert has_effect(rogue, "evading")
    assert rogue.hp == 10  # cost 2 HP


# ── Smoke Bomb (Rogue) ──

def test_smoke_bomb():
    rogue = _make_rogue()
    mob1 = _make_mob("A")
    mob2 = _make_mob("B")
    room = _make_room(mob1, mob2)
    events = resolve_ability(rogue, "smoke_bomb", "", room, 1, [rogue], _rooms(room))
    assert "smoke bomb" in events[0].result
    assert has_effect(mob1, "blinded")
    assert has_effect(mob2, "blinded")
    assert rogue.mp == 5  # cost 3


# ── Incapacitation ──

def test_asleep_cannot_act():
    w = _make_warrior()
    from effects import apply_effect
    apply_effect(w, StatusEffect("asleep", "enemy", 2))
    mob = _make_mob()
    room = _make_room(mob)
    events = resolve_ability(w, "attack", "Goblin", room, 1, [w], _rooms(room))
    assert "asleep" in events[0].result
    assert mob.hp == 10  # no damage dealt


# ── Kill tracking ──

def test_attack_kills_mob():
    w = _make_warrior()
    mob = _make_mob(hp=3)
    room = _make_room(mob)
    events = resolve_ability(w, "attack", "Goblin", room, 1, [w], _rooms(room))
    assert "slain" in events[0].result.lower()
    assert mob.hp == 0
    assert not mob.alive
