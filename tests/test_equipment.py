"""Tests for class-specific equipment restrictions."""
from __future__ import annotations

from engine import can_equip, equip_item
from models import AgentState, Item
from world import _item_stat_str


def _make_agent(agent_class: str = "Warrior") -> AgentState:
    return AgentState(
        name="Test",
        personality="Test",
        agent_class=agent_class,
        hp=20,
        max_hp=20,
        mp=10,
        max_mp=10,
        weapon=Item(name="Starter Sword", slot="weapon", atk=2),
        armor=Item(name="Starter Armor", slot="armor", pdef=1),
        ring=Item(name="Starter Ring", slot="ring", mdmg=1),
        room_id="room_1",
    )


# ── can_equip ──


def test_can_equip_unrestricted():
    agent = _make_agent("Warrior")
    item = Item(name="Generic Sword", slot="weapon", atk=5)
    assert can_equip(agent, item) is True


def test_can_equip_class_allowed():
    agent = _make_agent("Warrior")
    item = Item(name="Battle Axe", slot="weapon", atk=7, allowed_classes=["Warrior", "Paladin"])
    assert can_equip(agent, item) is True


def test_can_equip_class_not_allowed():
    agent = _make_agent("Mage")
    item = Item(name="Battle Axe", slot="weapon", atk=7, allowed_classes=["Warrior", "Paladin"])
    assert can_equip(agent, item) is False


def test_can_equip_ring_unrestricted():
    """Rings with no allowed_classes can be equipped by anyone."""
    agent = _make_agent("Rogue")
    item = Item(name="Magic Ring", slot="ring", mdmg=5)
    assert can_equip(agent, item) is True


# ── equip_item with class restrictions ──


def test_equip_item_allowed_class():
    agent = _make_agent("Warrior")
    better_weapon = Item(name="Great Sword", slot="weapon", atk=8, allowed_classes=["Warrior"])
    equip_item(agent, better_weapon)
    assert agent.weapon.name == "Great Sword"


def test_equip_item_wrong_class():
    agent = _make_agent("Mage")
    warrior_weapon = Item(name="Great Sword", slot="weapon", atk=8, allowed_classes=["Warrior"])
    equip_item(agent, warrior_weapon)
    assert agent.weapon.name == "Starter Sword"  # unchanged


def test_equip_item_unrestricted_upgrade():
    agent = _make_agent("Ranger")
    better_weapon = Item(name="Elven Bow", slot="weapon", atk=6)
    equip_item(agent, better_weapon)
    assert agent.weapon.name == "Elven Bow"


def test_equip_item_not_better():
    agent = _make_agent("Warrior")
    worse_weapon = Item(name="Rusty Sword", slot="weapon", atk=1)
    equip_item(agent, worse_weapon)
    assert agent.weapon.name == "Starter Sword"  # unchanged — not better


# ── _item_stat_str with class info ──


def test_item_stat_str_no_restriction():
    item = Item(name="Sword", slot="weapon", atk=5)
    result = _item_stat_str(item, "Warrior")
    assert "[CANNOT USE]" not in result


def test_item_stat_str_can_use():
    item = Item(name="Sword", slot="weapon", atk=5, allowed_classes=["Warrior"])
    result = _item_stat_str(item, "Warrior")
    assert "[CANNOT USE]" not in result


def test_item_stat_str_cannot_use():
    item = Item(name="Battle Axe", slot="weapon", atk=7, allowed_classes=["Warrior"])
    result = _item_stat_str(item, "Mage")
    assert "[CANNOT USE]" in result


def test_item_stat_str_no_agent_class():
    """When no agent_class provided, never shows [CANNOT USE]."""
    item = Item(name="Battle Axe", slot="weapon", atk=7, allowed_classes=["Warrior"])
    result = _item_stat_str(item)
    assert "[CANNOT USE]" not in result
