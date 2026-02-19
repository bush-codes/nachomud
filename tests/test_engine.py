"""Tests for engine.py — resolve_action, witness routing, helpers."""
from __future__ import annotations

from unittest.mock import patch

from engine import (
    agents_in_room,
    all_agents_dead,
    check_boss_defeated,
    create_agents,
    equip_item,
    resolve_action,
    rooms_within_range,
    witness,
    witness_events,
    witness_private,
    witness_yell,
)
from models import AgentState, GameEvent, Item, Mob, NPC, Room


def test_create_agents():
    agents = create_agents()
    assert len(agents) == 3
    assert agents[0].name == "Kael"
    assert agents[1].name == "Lyria"
    assert agents[2].name == "Finn"
    assert all(a.room_id == "room_1" for a in agents)


def test_agents_in_room(mock_agent, mock_mage):
    mock_mage.room_id = "room_1"
    result = agents_in_room([mock_agent, mock_mage], "room_1")
    assert "Kael" in result
    assert "Lyria" in result


def test_agents_in_room_exclude(mock_agent, mock_mage):
    mock_mage.room_id = "room_1"
    result = agents_in_room([mock_agent, mock_mage], "room_1", exclude="Kael")
    assert "Kael" not in result
    assert "Lyria" in result


def test_equip_item_better_weapon(mock_agent):
    better_weapon = Item(name="Great Sword", slot="weapon", atk=10)
    equip_item(mock_agent, better_weapon)
    assert mock_agent.weapon == better_weapon


def test_equip_item_worse_weapon(mock_agent):
    worse_weapon = Item(name="Stick", slot="weapon", atk=1)
    original = mock_agent.weapon
    equip_item(mock_agent, worse_weapon)
    assert mock_agent.weapon == original


def test_equip_item_better_armor(mock_agent):
    better_armor = Item(name="Plate", slot="armor", pdef=8)
    equip_item(mock_agent, better_armor)
    assert mock_agent.armor == better_armor


def test_equip_item_better_ring(mock_agent):
    better_ring = Item(name="Fire Ring", slot="ring", mdmg=5)
    equip_item(mock_agent, better_ring)
    assert mock_agent.ring == better_ring


def test_resolve_action_move(mock_agent, mock_rooms):
    with patch("engine.describe_room"):
        events = resolve_action(mock_agent, "n", "", mock_rooms, [mock_agent], tick=1)
    assert len(events) == 1
    assert "moves north" in events[0].result
    assert mock_agent.room_id == "room_2"


def test_resolve_action_move_no_exit(mock_agent, mock_rooms):
    events = resolve_action(mock_agent, "w", "", mock_rooms, [mock_agent], tick=1)
    assert "No exit" in events[0].result
    assert mock_agent.room_id == "room_1"


def test_resolve_action_attack(mock_agent, mock_rooms):
    events = resolve_action(mock_agent, "attack", "Goblin Scout", mock_rooms, [mock_agent], tick=1)
    assert len(events) >= 1
    assert "attacks" in events[0].result


def test_resolve_action_say(mock_agent, mock_rooms, mock_mage):
    mock_mage.room_id = "room_1"
    events = resolve_action(mock_agent, "say", "Hello friends", mock_rooms, [mock_agent, mock_mage], tick=1)
    assert len(events) == 1
    assert "says" in events[0].result
    assert events[0].category == "comm"


def test_resolve_action_get_item(mock_agent, mock_rooms):
    sword = Item(name="Magic Sword", slot="weapon", atk=10)
    mock_rooms["room_1"].items.append(sword)
    events = resolve_action(mock_agent, "get", "Magic Sword", mock_rooms, [mock_agent], tick=1)
    assert "picks up" in events[0].result
    assert sword in mock_agent.inventory


def test_resolve_action_yell(mock_agent, mock_rooms):
    events = resolve_action(mock_agent, "yell", "Help!", mock_rooms, [mock_agent], tick=1)
    assert "yells" in events[0].result
    assert events[0].category == "comm"


def test_check_boss_defeated():
    boss = Mob(name="Boss", hp=0, max_hp=30, atk=6, is_boss=True)
    rooms = {"r1": Room(id="r1", name="Boss Room", mobs=[boss])}
    assert check_boss_defeated(rooms) is True


def test_check_boss_not_defeated():
    boss = Mob(name="Boss", hp=10, max_hp=30, atk=6, is_boss=True)
    rooms = {"r1": Room(id="r1", name="Boss Room", mobs=[boss])}
    assert check_boss_defeated(rooms) is False


def test_all_agents_dead(mock_agent, mock_mage):
    mock_agent.alive = False
    mock_mage.alive = False
    assert all_agents_dead([mock_agent, mock_mage]) is True


def test_not_all_agents_dead(mock_agent, mock_mage):
    mock_agent.alive = False
    assert all_agents_dead([mock_agent, mock_mage]) is False


def test_rooms_within_range():
    rooms = {
        "r1": Room(id="r1", name="Start", exits={"n": "r2"}),
        "r2": Room(id="r2", name="Mid", exits={"s": "r1", "n": "r3"}),
        "r3": Room(id="r3", name="Far", exits={"s": "r2"}),
    }
    result = rooms_within_range("r1", rooms, max_hops=2)
    assert "r1" in result
    assert "r2" in result
    assert "r3" in result
    assert result["r1"][0] == 0
    assert result["r2"][0] == 1
    assert result["r3"][0] == 2


# ── Witness tests ──

def test_witness_action(mock_agent, mock_mage):
    mock_mage.room_id = "room_1"
    witness([mock_agent, mock_mage], "Kael attacks Goblin", "room_1", "Kael")
    assert ">> Kael attacks Goblin" in mock_agent.action_history
    assert "Kael attacks Goblin" in mock_mage.action_history


def test_witness_comm(mock_agent, mock_mage):
    mock_mage.room_id = "room_1"
    witness([mock_agent, mock_mage], "Kael says: hello", "room_1", "Kael", history="comm", skip_sender=True)
    assert len(mock_agent.comm_history) == 0  # sender skipped
    assert "Kael says: hello" in mock_mage.comm_history


def test_witness_private(mock_agent, mock_mage):
    mock_mage.room_id = "room_1"
    witness_private([mock_agent, mock_mage], "secret message", "Kael", "Lyria")
    assert ">> secret message" in mock_agent.comm_history
    assert "secret message" in mock_mage.comm_history


def test_witness_yell(mock_agent, mock_mage):
    mock_mage.room_id = "room_2"
    rooms = {
        "room_1": Room(id="room_1", name="Entry", exits={"n": "room_2"}),
        "room_2": Room(id="room_2", name="Barracks", exits={"s": "room_1"}),
    }
    witness_yell([mock_agent, mock_mage], rooms, "Kael", "Help!", "room_1")
    # Kael is sender, should NOT get it
    assert len(mock_agent.comm_history) == 0
    # Lyria in adjacent room should hear the yell from the south
    assert len(mock_mage.comm_history) == 1
    assert "yells from the south" in mock_mage.comm_history[0]
