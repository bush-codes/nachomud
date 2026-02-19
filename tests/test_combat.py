"""Tests for combat.py — resolve functions, counterattack, poison ticks."""
from __future__ import annotations

import math

from combat import (
    mob_counterattack,
    resolve_attack,
    resolve_fireball,
    resolve_heal,
    resolve_missile,
    resolve_poison,
    tick_poison,
)
from models import AgentState, Item, Mob, Room


def test_resolve_attack_hit(mock_agent, mock_room):
    events = resolve_attack(mock_agent, mock_room, "Goblin Scout", tick=1)
    assert len(events) >= 1
    assert "attacks" in events[0].result
    # weapon.atk=5, mob has no pdef, so 5 damage → clamped to 0
    assert mock_room.mobs[0].hp == 0
    assert "slain" in events[0].result.lower()


def test_resolve_attack_miss_target(mock_agent, mock_room):
    events = resolve_attack(mock_agent, mock_room, "Dragon", tick=1)
    assert len(events) == 1
    assert "No enemy named" in events[0].result or "Dragon" in events[0].result


def test_resolve_attack_counterattack(mock_agent):
    mob = Mob(name="Strong Goblin", hp=20, max_hp=20, atk=3)
    room = Room(id="r1", name="Test", mobs=[mob])
    events = resolve_attack(mock_agent, room, "Strong Goblin", tick=1)
    # Should have attack event + counterattack event
    assert len(events) == 2
    assert "retaliates" in events[1].result


def test_resolve_missile(mock_mage, mock_room):
    events = resolve_missile(mock_mage, mock_room, "Goblin Scout", tick=1)
    assert len(events) >= 1
    assert "missile" in events[0].result.lower() or "magic" in events[0].result.lower()
    assert mock_mage.mp == 24  # cost 1 MP (25 - 1)


def test_resolve_missile_no_mp(mock_mage, mock_room):
    mock_mage.mp = 0
    events = resolve_missile(mock_mage, mock_room, "Goblin Scout", tick=1)
    assert "Not enough MP" in events[0].result


def test_resolve_fireball(mock_mage):
    mob1 = Mob(name="Goblin A", hp=4, max_hp=4, atk=2)
    mob2 = Mob(name="Goblin B", hp=4, max_hp=4, atk=2)
    room = Room(id="r1", name="Test", mobs=[mob1, mob2])
    events = resolve_fireball(mock_mage, room, tick=1)
    assert "fireball" in events[0].result.lower()
    assert mock_mage.mp == 22  # cost 3 MP (25 - 3)


def test_resolve_fireball_no_mobs(mock_mage):
    room = Room(id="r1", name="Empty")
    events = resolve_fireball(mock_mage, room, tick=1)
    assert "No enemies" in events[0].result


def test_resolve_poison(mock_mage, mock_room):
    events = resolve_poison(mock_mage, mock_room, "Goblin Scout", tick=1)
    assert "poisons" in events[0].result
    assert mock_room.mobs[0].poison_remaining == 3
    assert mock_mage.mp == 23  # cost 2 MP (25 - 2)


def test_resolve_heal_self(mock_mage):
    mock_mage.hp = 4
    room = Room(id="r1", name="Test")
    events = resolve_heal(mock_mage, tick=1, target_name="", room=room)
    assert "heals" in events[0].result
    heal_amount = math.ceil(mock_mage.max_hp * 0.3)
    assert mock_mage.hp == 4 + heal_amount


def test_resolve_heal_ally(mock_mage, mock_agent):
    mock_agent.hp = 5
    mock_agent.room_id = mock_mage.room_id
    room = Room(id=mock_mage.room_id, name="Test")
    events = resolve_heal(mock_mage, tick=1, target_name="Kael", allies=[mock_agent, mock_mage], room=room)
    assert "heals Kael" in events[0].result
    heal_amount = math.ceil(mock_agent.max_hp * 0.3)
    assert mock_agent.hp == 5 + heal_amount


def test_resolve_heal_no_mp(mock_mage):
    mock_mage.mp = 0
    room = Room(id=mock_mage.room_id, name="Test")
    events = resolve_heal(mock_mage, tick=1, room=room)
    assert "Not enough MP" in events[0].result


def test_mob_counterattack(mock_agent, mock_mob):
    old_hp = mock_agent.hp
    events = mob_counterattack(mock_agent, mock_mob, tick=1)
    assert len(events) == 1
    assert "retaliates" in events[0].result
    # mob.atk=2, agent pdef=3+0=3 from armor+ring → 2-3=-1 → min 1 (since mob.atk > 0)
    expected_damage = 1  # min 1 when mob.atk > 0
    assert mock_agent.hp == old_hp - expected_damage


def test_mob_counterattack_kills_agent(mock_mage, mock_boss):
    # Mage has 8 HP, boss atk=6, mage pdef=1 → damage=5
    mock_mage.hp = 8  # ensure starting HP
    events = mob_counterattack(mock_mage, mock_boss, tick=1)
    assert mock_mage.hp == 3  # 8 - 5 = 3, not dead yet
    # Hit again
    events2 = mob_counterattack(mock_mage, mock_boss, tick=2)
    assert mock_mage.hp == 0
    assert not mock_mage.alive
    assert "fallen" in events2[0].result.lower()


def test_tick_poison(mock_room):
    mock_room.mobs[0].poison_remaining = 3
    events = tick_poison(mock_room, tick=1)
    assert len(events) == 1
    assert "poison" in events[0].result.lower()
    assert mock_room.mobs[0].hp == 3  # 4 - 1
    assert mock_room.mobs[0].poison_remaining == 2


def test_tick_poison_kills_mob():
    mob = Mob(name="Weak Goblin", hp=1, max_hp=4, atk=1, poison_remaining=2)
    room = Room(id="r1", name="Test", mobs=[mob])
    events = tick_poison(room, tick=1)
    assert mob.hp == 0
    assert "succumbs" in events[0].result
