"""Tests for agent.py — parsing, validation, command building."""
from __future__ import annotations

from agent import (
    _is_valid_action,
    _parse_think_comm,
    _parse_think_do,
    build_valid_actions,
    parse_action,
)
from config import ABILITY_DEFINITIONS
from models import AgentState, Item, Mob, NPC, Room


# ── parse_action ──

def test_parse_action_simple():
    assert parse_action("attack Goblin") == ("attack", "Goblin")


def test_parse_action_direction():
    assert parse_action("n") == ("n", "")
    assert parse_action("north") == ("n", "")
    assert parse_action("move north") == ("n", "")
    assert parse_action("go east") == ("e", "")


def test_parse_action_empty():
    cmd, arg = parse_action("")
    assert cmd == "say"


def test_parse_action_tell():
    assert parse_action("tell Kael hello friend") == ("tell", "Kael hello friend")


def test_parse_action_slash_prefix():
    # _parse_think_do strips "/" prefix, but parse_action doesn't
    cmd, arg = parse_action("heal Lyria")
    assert cmd == "heal"
    assert arg == "Lyria"


# ── _parse_think_do ──

def test_parse_think_do_basic():
    raw = "Think: I should attack\nDo: attack Goblin"
    think, action = _parse_think_do(raw)
    assert think == "I should attack"
    assert action == "attack Goblin"


def test_parse_think_do_multiline_think():
    raw = "Think: First point.\nSecond point.\nDo: n"
    think, action = _parse_think_do(raw)
    assert "First point" in think
    assert "Second point" in think
    assert action == "n"


def test_parse_think_do_fallback():
    raw = "I'll go north\nn"
    think, action = _parse_think_do(raw)
    assert action == "n"


# ── _parse_think_comm ──

def test_parse_think_comm_none():
    raw = "Think: Nothing to say\nComm: none"
    think, comm = _parse_think_comm(raw)
    assert think == "Nothing to say"
    assert comm is None


def test_parse_think_comm_action():
    raw = "Think: I need to warn them\nComm: yell Watch out!"
    think, comm = _parse_think_comm(raw)
    assert think == "I need to warn them"
    assert comm == "yell Watch out!"


# ── _is_valid_action ──

def test_is_valid_action_move(mock_agent, mock_room):
    assert _is_valid_action("n", "", mock_room, mock_agent, []) is True
    assert _is_valid_action("e", "", mock_room, mock_agent, []) is False


def test_is_valid_action_attack(mock_agent, mock_room):
    assert _is_valid_action("attack", "Goblin Scout", mock_room, mock_agent, []) is True
    assert _is_valid_action("attack", "Dragon", mock_room, mock_agent, []) is False


def test_is_valid_action_ability_class_check(mock_mage, mock_agent):
    """Mage doesn't have 'heal' — that's Cleric. But Mage has 'missile'."""
    room = Room(id="room_1", name="Test")
    mock_agent.room_id = "room_1"
    # Mage doesn't have heal
    assert _is_valid_action("heal", "", room, mock_mage, [mock_agent]) is False
    # Mage has missile
    mob = Mob(name="Goblin", hp=5, max_hp=5, atk=2)
    room_with_mob = Room(id="room_1", name="Test", mobs=[mob])
    assert _is_valid_action("missile", "Goblin", room_with_mob, mock_mage, [mock_agent]) is True


def test_is_valid_action_get(mock_agent):
    item = Item(name="Magic Sword", slot="weapon", atk=10)
    room = Room(id="room_1", name="Test", items=[item])
    assert _is_valid_action("get", "Magic Sword", room, mock_agent, []) is True
    assert _is_valid_action("get", "Shield", room, mock_agent, []) is False


# ── build_valid_actions ──

def test_build_valid_actions(mock_agent, mock_room):
    actions = build_valid_actions(mock_agent, mock_room, [mock_agent])
    assert any("north" in a.lower() for a in actions)
    assert any("attack" in a.lower() for a in actions)
