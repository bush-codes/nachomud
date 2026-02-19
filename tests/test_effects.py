"""Tests for effects.py — buff/debuff system."""
from __future__ import annotations

from effects import (
    apply_effect,
    clear_debuffs,
    consume_effect,
    get_effect,
    has_effect,
    is_incapacitated,
    modify_incoming_damage,
    modify_outgoing_damage,
    modify_source_damage,
    tick_effects,
)
from models import AgentState, Item, Mob, StatusEffect


def _make_agent(name="Kael", hp=25, max_hp=25) -> AgentState:
    return AgentState(
        name=name, personality="", agent_class="Warrior",
        hp=hp, max_hp=max_hp, mp=10, max_mp=10,
        weapon=Item("Sword", "weapon", atk=5),
        armor=Item("Armor", "armor", pdef=3),
        ring=Item("Ring", "ring", mdmg=1),
    )


def _make_mob(name="Goblin", hp=10, max_hp=10) -> Mob:
    return Mob(name=name, hp=hp, max_hp=max_hp, atk=3)


# ── apply_effect ──

def test_apply_effect_new():
    agent = _make_agent()
    apply_effect(agent, StatusEffect("defending", "Kael", 1))
    assert has_effect(agent, "defending")


def test_apply_effect_refresh():
    agent = _make_agent()
    apply_effect(agent, StatusEffect("warded", "Sera", 2, value=3))
    apply_effect(agent, StatusEffect("warded", "Sera", 3, value=3))
    assert len([e for e in agent.status_effects if e.name == "warded"]) == 1
    assert get_effect(agent, "warded").remaining_ticks == 3


def test_apply_effect_no_stack():
    agent = _make_agent()
    apply_effect(agent, StatusEffect("poisoned", "enemy", 3, value=2))
    apply_effect(agent, StatusEffect("poisoned", "enemy2", 3, value=2))
    assert len([e for e in agent.status_effects if e.name == "poisoned"]) == 1


# ── has_effect / get_effect ──

def test_has_effect_false():
    agent = _make_agent()
    assert not has_effect(agent, "defending")


def test_get_effect_none():
    agent = _make_agent()
    assert get_effect(agent, "warded") is None


# ── consume_effect ──

def test_consume_effect():
    agent = _make_agent()
    apply_effect(agent, StatusEffect("evading", "Shade", -1))
    consumed = consume_effect(agent, "evading")
    assert consumed is not None
    assert consumed.name == "evading"
    assert not has_effect(agent, "evading")


def test_consume_effect_not_found():
    agent = _make_agent()
    assert consume_effect(agent, "evading") is None


# ── clear_debuffs ──

def test_clear_debuffs():
    agent = _make_agent()
    apply_effect(agent, StatusEffect("poisoned", "enemy", 3, value=2))
    apply_effect(agent, StatusEffect("cursed", "enemy", 3, value=2))
    apply_effect(agent, StatusEffect("defending", "self", 1))  # buff — should stay
    cleared = clear_debuffs(agent)
    assert "poisoned" in cleared
    assert "cursed" in cleared
    assert has_effect(agent, "defending")
    assert not has_effect(agent, "poisoned")


def test_clear_debuffs_empty():
    agent = _make_agent()
    cleared = clear_debuffs(agent)
    assert cleared == []


# ── is_incapacitated ──

def test_is_incapacitated_asleep():
    mob = _make_mob()
    apply_effect(mob, StatusEffect("asleep", "Finn", 2))
    assert is_incapacitated(mob)


def test_is_incapacitated_awake():
    mob = _make_mob()
    assert not is_incapacitated(mob)


# ── tick_effects: DoT ──

def test_tick_effects_poison():
    mob = _make_mob(hp=10)
    apply_effect(mob, StatusEffect("poisoned", "Finn", 3, value=2))
    events = tick_effects(mob, tick=1, room_id="r1")
    assert len(events) == 1
    assert mob.hp == 8
    assert "poison" in events[0].result.lower()
    assert has_effect(mob, "poisoned")
    assert get_effect(mob, "poisoned").remaining_ticks == 2


def test_tick_effects_poison_kills():
    mob = _make_mob(hp=1)
    apply_effect(mob, StatusEffect("poisoned", "Finn", 3, value=2))
    events = tick_effects(mob, tick=1, room_id="r1")
    assert mob.hp == 0
    assert not mob.alive
    assert "succumbs" in events[0].result


def test_tick_effects_curse():
    agent = _make_agent(hp=10)
    apply_effect(agent, StatusEffect("cursed", "enemy", 3, value=2))
    events = tick_effects(agent, tick=1)
    assert agent.hp == 8
    assert "curse" in events[0].result.lower()


def test_tick_effects_bleed():
    agent = _make_agent(hp=10)
    apply_effect(agent, StatusEffect("bleeding", "Shade", 3, value=2))
    events = tick_effects(agent, tick=1)
    assert agent.hp == 8
    assert "bleed" in events[0].result.lower()


def test_tick_effects_expiry():
    agent = _make_agent()
    apply_effect(agent, StatusEffect("defending", "self", 1))
    tick_effects(agent, tick=1)
    assert not has_effect(agent, "defending")


def test_tick_effects_duration_countdown():
    agent = _make_agent()
    apply_effect(agent, StatusEffect("warded", "Sera", 3, value=3))
    tick_effects(agent, tick=1)
    assert has_effect(agent, "warded")
    assert get_effect(agent, "warded").remaining_ticks == 2
    tick_effects(agent, tick=2)
    assert get_effect(agent, "warded").remaining_ticks == 1
    tick_effects(agent, tick=3)
    assert not has_effect(agent, "warded")


def test_tick_effects_consumable_not_decremented():
    agent = _make_agent()
    apply_effect(agent, StatusEffect("evading", "Shade", -1))
    tick_effects(agent, tick=1)
    assert has_effect(agent, "evading")  # should persist


# ── modify_incoming_damage ──

def test_modify_incoming_evade():
    agent = _make_agent()
    apply_effect(agent, StatusEffect("evading", "self", -1))
    damage = modify_incoming_damage(agent, 10)
    assert damage == 0
    assert not has_effect(agent, "evading")  # consumed


def test_modify_incoming_defend():
    agent = _make_agent()
    apply_effect(agent, StatusEffect("defending", "self", 1))
    damage = modify_incoming_damage(agent, 10)
    assert damage == 5  # ceil(10 * 0.5)


def test_modify_incoming_ward():
    agent = _make_agent()
    apply_effect(agent, StatusEffect("warded", "Sera", 3, value=3))
    damage = modify_incoming_damage(agent, 10)
    assert damage == 7  # 10 - 3


def test_modify_incoming_barrier_partial():
    agent = _make_agent()
    apply_effect(agent, StatusEffect("barrier", "Lyria", -1, value=8))
    damage = modify_incoming_damage(agent, 5)
    assert damage == 0
    assert has_effect(agent, "barrier")
    assert get_effect(agent, "barrier").value == 3  # 8 - 5


def test_modify_incoming_barrier_depleted():
    agent = _make_agent()
    apply_effect(agent, StatusEffect("barrier", "Lyria", -1, value=5))
    damage = modify_incoming_damage(agent, 10)
    assert damage == 5  # 10 - 5
    assert not has_effect(agent, "barrier")  # consumed


def test_modify_incoming_defend_and_ward_stack():
    agent = _make_agent()
    apply_effect(agent, StatusEffect("defending", "self", 1))
    apply_effect(agent, StatusEffect("warded", "Sera", 3, value=3))
    damage = modify_incoming_damage(agent, 10)
    # defend: ceil(10 * 0.5) = 5, then ward: 5 - 3 = 2
    assert damage == 2


# ── modify_outgoing_damage ──

def test_modify_outgoing_rally():
    agent = _make_agent()
    apply_effect(agent, StatusEffect("rallied", "Kael", -1, value=2))
    damage = modify_outgoing_damage(agent, 5)
    assert damage == 7  # 5 + 2
    assert not has_effect(agent, "rallied")  # consumed


def test_modify_outgoing_no_rally():
    agent = _make_agent()
    damage = modify_outgoing_damage(agent, 5)
    assert damage == 5


# ── modify_source_damage (blinded) ──

def test_modify_source_damage_blinded():
    mob = _make_mob()
    apply_effect(mob, StatusEffect("blinded", "Shade", 2, value=3))
    damage = modify_source_damage(mob, 5)
    assert damage == 2  # 5 - 3


def test_modify_source_damage_not_blinded():
    mob = _make_mob()
    damage = modify_source_damage(mob, 5)
    assert damage == 5


# ── Chaining: multiple DoTs on same target ──

def test_multiple_dots():
    mob = _make_mob(hp=20)
    apply_effect(mob, StatusEffect("poisoned", "Finn", 3, value=2))
    apply_effect(mob, StatusEffect("bleeding", "Shade", 3, value=2))
    events = tick_effects(mob, tick=1, room_id="r1")
    assert len(events) == 2
    assert mob.hp == 16  # 20 - 2 - 2
