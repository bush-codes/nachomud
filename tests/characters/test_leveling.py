"""Tests for leveling.py — XP thresholds, HP/prof/ability/stat changes."""
from __future__ import annotations

import pytest

from nachomud.characters.character import create_character
from nachomud.characters.leveling import (
    LevelUp,
    apply_all_pending_level_ups,
    apply_one_level_up,
    can_level_up,
    render_level_up,
    xp_to_next_level,
)
from nachomud.rules.stats import Stats


def _aric(level: int = 1, xp: int = 0):
    s = Stats(STR=15, DEX=12, CON=14, INT=8, WIS=10, CHA=13)
    a = create_character("Aric", "Dwarf", "Warrior", s, level=level, player_id="p1")
    a.xp = xp
    return a


# ── XP thresholds ──

def test_l1_to_l2_threshold_300():
    a = _aric(level=1, xp=0)
    assert xp_to_next_level(a) == 300
    a.xp = 299
    assert not can_level_up(a)
    a.xp = 300
    assert can_level_up(a)


def test_max_level_no_more_xp():
    a = _aric(level=10, xp=64000)
    assert not can_level_up(a)
    assert xp_to_next_level(a) > 1_000_000


# ── HP gain ──

def test_hp_increases_per_level():
    a = _aric(level=1, xp=300)
    before_hp = a.max_hp
    apply_one_level_up(a)
    assert a.max_hp > before_hp
    # Player is healed to new max
    assert a.hp == a.max_hp


def test_proficiency_bonus_bumps_at_l5():
    a = _aric(level=4, xp=6500)
    assert a.proficiency_bonus == 2
    apply_one_level_up(a)
    assert a.level == 5
    assert a.proficiency_bonus == 3


# ── Stat increase at L4 ──

def test_stat_increase_at_l4_primary():
    a = _aric(level=3, xp=2700)
    str_before = a.stats["STR"]
    lu = apply_one_level_up(a)
    assert a.level == 4
    assert lu.stat_increase is not None
    stat, amt = lu.stat_increase
    assert stat == "STR"
    assert amt == 2
    assert a.stats["STR"] == str_before + 2


def test_stat_increase_caps_at_20():
    a = _aric(level=3, xp=2700)
    a.stats["STR"] = 20  # already maxed
    lu = apply_one_level_up(a)
    assert lu.stat_increase is None
    assert a.stats["STR"] == 20


def test_no_stat_increase_at_other_levels():
    a = _aric(level=1, xp=300)
    lu = apply_one_level_up(a)
    assert a.level == 2
    assert lu.stat_increase is None


# ── Ability unlocks ──

def test_l3_unlocks_warrior_taunt():
    a = _aric(level=2, xp=900)
    a.abilities = ["attack", "defend"]
    lu = apply_one_level_up(a)
    assert a.level == 3
    assert "taunt" in a.abilities
    assert lu.abilities_unlocked == ["taunt"]


def test_l5_unlocks_warrior_cleave():
    a = _aric(level=4, xp=6500)
    a.abilities = ["attack", "defend", "taunt"]
    lu = apply_one_level_up(a)
    assert "cleave" in a.abilities
    assert lu.abilities_unlocked == ["cleave"]


def test_l7_unlocks_warrior_rally():
    a = _aric(level=6, xp=23000)
    a.abilities = ["attack", "defend", "taunt", "cleave"]
    lu = apply_one_level_up(a)
    assert "rally" in a.abilities


def test_no_double_unlock():
    a = _aric(level=2, xp=900)
    a.abilities = ["attack", "defend", "taunt"]  # taunt already there
    lu = apply_one_level_up(a)
    assert lu.abilities_unlocked == []  # didn't double-add


# ── Walking up multiple levels in one go ──

def test_apply_all_pending_walks_through_thresholds():
    a = _aric(level=1, xp=900)  # enough for L3 (300 + 600 cumulative)
    out = apply_all_pending_level_ups(a)
    assert len(out) == 2
    assert a.level == 3


def test_apply_all_pending_jumps_to_l4():
    a = _aric(level=1, xp=2700)  # enough for L4
    out = apply_all_pending_level_ups(a)
    assert len(out) == 3
    assert a.level == 4
    assert any(lu.stat_increase is not None for lu in out)


def test_apply_all_pending_no_op_when_under_threshold():
    a = _aric(level=1, xp=100)
    assert apply_all_pending_level_ups(a) == []
    assert a.level == 1


# ── Rendering ──

def test_render_level_up_includes_summary():
    lu = LevelUp(
        new_level=3, hp_gained=8, new_max_hp=21, new_prof_bonus=2,
        abilities_unlocked=["taunt"], stat_increase=None,
    )
    text = render_level_up(lu, "Aric")
    assert "Level 3" in text
    assert "HP +8" in text
    assert "taunt" in text


# ── Cleric/Mage variations ──

def test_mage_unlocks_barrier_at_l3():
    s = Stats(STR=8, DEX=14, CON=12, INT=15, WIS=13, CHA=10)
    a = create_character("Lyria", "Elf", "Mage", s, player_id="p2", level=2)
    a.xp = 900
    apply_one_level_up(a)
    assert "barrier" in a.abilities


def test_rogue_unlocks_evade_at_l3():
    s = Stats(STR=8, DEX=15, CON=14, INT=13, WIS=10, CHA=12)
    a = create_character("Shade", "Halfling", "Rogue", s, player_id="p3", level=2)
    a.xp = 900
    apply_one_level_up(a)
    assert "evade" in a.abilities
