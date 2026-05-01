"""Tests for char_create.py — character creation state machine."""
from __future__ import annotations

import pytest

from nachomud.characters.creation import CharCreator
from nachomud.rules.stats import POINT_BUY_BUDGET


def _drive(cc: CharCreator, *inputs: str) -> CharCreator:
    cc.start()
    for inp in inputs:
        cc.handle_input(inp)
    return cc


# ── Happy path ──

def test_full_flow_dwarf_warrior_standard():
    cc = CharCreator()
    cc.start()
    assert cc.state == "name"

    cc.handle_input("Aric")
    assert cc.state == "race"
    assert cc.name == "Aric"

    cc.handle_input("2")  # Dwarf
    assert cc.state == "class"
    assert cc.race == "Dwarf"

    cc.handle_input("1")  # Warrior
    assert cc.state == "point_buy"
    assert cc.class_name == "Warrior"

    cc.handle_input("standard")
    assert cc.state == "confirm"

    cc.handle_input("y")
    assert cc.is_complete()
    a = cc.build_agent()
    assert a.name == "Aric"
    assert a.race == "Dwarf"
    assert a.agent_class == "Warrior"
    # Standard array assigns primary (STR) first: STR=15, then DEX=14, CON=13, INT=12, WIS=10, CHA=8
    # +Dwarf: STR 16, CON 15
    assert a.stats["STR"] == 16
    assert a.stats["CON"] == 15
    # HP = d10 + CON mod (15 → +2) = 12
    assert a.max_hp == 12
    assert a.ac == 18  # 16 base + min(DEX 14 mod +2, max 2) = 18


def test_full_flow_custom_point_buy():
    cc = CharCreator()
    cc.start()
    cc.handle_input("Lyria")
    cc.handle_input("Elf")
    cc.handle_input("Mage")
    # Stepwise: STR 8, DEX 14, CON 12, INT 15, WIS 13, CHA 10
    # Costs: 0+7+4+9+5+2 = 27
    for v in (8, 14, 12, 15, 13, 10):
        cc.handle_input(str(v))
    assert cc.state == "confirm"
    cc.handle_input("y")
    a = cc.build_agent()
    # Elf: +2 DEX, +1 INT
    assert a.stats["DEX"] == 16
    assert a.stats["INT"] == 16


# ── Validation ──

def test_invalid_name_too_long():
    cc = CharCreator()
    cc.start()
    cc.handle_input("X" * 30)
    assert cc.state == "name"  # didn't advance


def test_invalid_name_special_chars():
    cc = CharCreator()
    cc.start()
    cc.handle_input("Aric$$$")
    assert cc.state == "name"


def test_unknown_race():
    cc = CharCreator()
    cc.start()
    cc.handle_input("Aric")
    cc.handle_input("Goblin")
    assert cc.state == "race"  # didn't advance


def test_race_pick_by_name_prefix():
    cc = CharCreator()
    cc.start()
    cc.handle_input("Aric")
    cc.handle_input("Dwa")
    assert cc.race == "Dwarf"


def test_class_pick_by_name():
    cc = CharCreator()
    cc.start()
    cc.handle_input("Aric")
    cc.handle_input("Human")
    cc.handle_input("Mage")
    assert cc.class_name == "Mage"


def test_point_buy_overspend_rejected():
    cc = CharCreator()
    cc.start()
    cc.handle_input("Aric")
    cc.handle_input("Human")
    cc.handle_input("Warrior")
    # Try to set everything to 15 (cost 9 each = 54, way over 27)
    cc.handle_input("15")  # STR ok (cost 9)
    cc.handle_input("15")  # DEX ok (cumulative cost 18)
    cc.handle_input("15")  # CON would be cost 27, ok
    cc.handle_input("15")  # INT would be cost 36, REJECTED
    # Should still be on INT
    assert cc.state == "point_buy"
    assert cc.current_stat_idx == 3


def test_point_buy_below_min():
    cc = CharCreator()
    cc.start()
    cc.handle_input("Aric")
    cc.handle_input("Human")
    cc.handle_input("Warrior")
    cc.handle_input("7")  # below 8
    assert cc.current_stat_idx == 0


def test_point_buy_above_max():
    cc = CharCreator()
    cc.start()
    cc.handle_input("Aric")
    cc.handle_input("Human")
    cc.handle_input("Warrior")
    cc.handle_input("16")  # above 15
    assert cc.current_stat_idx == 0


def test_restart_resets_state():
    cc = CharCreator()
    cc.start()
    cc.handle_input("Aric")
    cc.handle_input("Dwarf")
    cc.handle_input("restart")
    assert cc.state == "name"
    assert cc.name == ""
    assert cc.race == ""


def test_confirm_no_restarts():
    cc = CharCreator()
    cc.start()
    cc.handle_input("Aric")
    cc.handle_input("Human")
    cc.handle_input("Warrior")
    cc.handle_input("standard")
    assert cc.state == "confirm"
    cc.handle_input("n")
    assert cc.state == "name"


def test_build_agent_before_complete_raises():
    cc = CharCreator()
    with pytest.raises(RuntimeError):
        cc.build_agent()


# ── Standard-array assignment by primary stat ──

def test_standard_array_assigns_primary_first():
    # Mage primary is INT
    cc = CharCreator()
    cc.start()
    cc.handle_input("X")
    cc.handle_input("Human")
    cc.handle_input("Mage")
    cc.handle_input("standard")
    cc.handle_input("y")
    a = cc.build_agent()
    # INT should be 15 (pre-racial); +1 Human = 16
    assert a.stats["INT"] == 16
    # Other stats from 14,13,12,10,8 + Human +1 each


def test_standard_array_for_rogue_uses_dex():
    cc = CharCreator()
    cc.start()
    cc.handle_input("Shade")
    cc.handle_input("Halfling")
    cc.handle_input("Rogue")
    cc.handle_input("standard")
    cc.handle_input("y")
    a = cc.build_agent()
    # Rogue primary DEX, gets 15. Halfling +2 DEX = 17.
    assert a.stats["DEX"] == 17


# ── Agent attributes after creation ──

def test_built_agent_has_starting_abilities():
    cc = CharCreator()
    cc.start()
    cc.handle_input("Kael")
    cc.handle_input("Human")
    cc.handle_input("Warrior")
    cc.handle_input("standard")
    cc.handle_input("y")
    a = cc.build_agent()
    assert "attack" in a.abilities
    assert "defend" in a.abilities


def test_built_agent_at_spawn_room():
    cc = CharCreator(spawn_room="silverbrook.inn")
    cc.start()
    cc.handle_input("Kael")
    cc.handle_input("Human")
    cc.handle_input("Warrior")
    cc.handle_input("standard")
    cc.handle_input("y")
    a = cc.build_agent()
    assert a.room_id == "silverbrook.inn"
    assert a.respawn_room == "silverbrook.inn"


def test_built_agent_has_world_id():
    cc = CharCreator(default_world_id="custom_world", spawn_room="silverbrook.inn")
    cc.start()
    cc.handle_input("Kael")
    cc.handle_input("Human")
    cc.handle_input("Warrior")
    cc.handle_input("standard")
    cc.handle_input("y")
    a = cc.build_agent()
    assert a.world_id == "custom_world"
