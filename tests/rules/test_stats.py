"""Tests for stats.py — modifiers, point-buy, racial mods, derived values."""
from __future__ import annotations

import pytest

from nachomud.rules.stats import (
    POINT_BUY_BUDGET,
    Stats,
    apply_racial_mods,
    attack_bonus,
    compute_ac,
    compute_max_hp,
    initiative_bonus,
    mod,
    point_buy_cost,
    proficiency_bonus,
    save_bonus,
    spell_attack_bonus,
    spell_save_dc,
    validate_point_buy,
)


# ── Modifiers ──

@pytest.mark.parametrize("stat,expected", [
    (1, -5), (3, -4), (8, -1), (10, 0), (11, 0), (12, 1), (14, 2),
    (15, 2), (16, 3), (18, 4), (20, 5), (30, 10),
])
def test_modifier(stat, expected):
    assert mod(stat) == expected


# ── Proficiency bonus ──

@pytest.mark.parametrize("level,expected", [
    (1, 2), (4, 2), (5, 3), (8, 3), (9, 4), (12, 4), (13, 5), (16, 5), (17, 6), (20, 6),
])
def test_proficiency_bonus(level, expected):
    assert proficiency_bonus(level) == expected


# ── Point-buy ──

def test_standard_array_costs_27():
    s = Stats(STR=15, DEX=14, CON=13, INT=12, WIS=10, CHA=8)
    assert point_buy_cost(s) == 27
    ok, _ = validate_point_buy(s)
    assert ok


def test_overspend_fails():
    s = Stats(STR=15, DEX=15, CON=15, INT=15, WIS=15, CHA=15)
    ok, reason = validate_point_buy(s)
    assert not ok
    assert "budget" in reason.lower()


def test_below_min_fails():
    s = Stats(STR=7, DEX=10, CON=10, INT=10, WIS=10, CHA=10)
    ok, reason = validate_point_buy(s)
    assert not ok
    assert "out of range" in reason.lower()


def test_above_max_fails():
    s = Stats(STR=16, DEX=10, CON=10, INT=10, WIS=10, CHA=10)
    ok, reason = validate_point_buy(s)
    assert not ok
    assert "out of range" in reason.lower()


def test_underspend_allowed():
    s = Stats(STR=8, DEX=8, CON=8, INT=8, WIS=8, CHA=8)
    ok, _ = validate_point_buy(s)
    assert ok  # spending 0 of 27 is allowed (just not optimal)


def test_budget_constant():
    assert POINT_BUY_BUDGET == 27


# ── Racial mods ──

def test_apply_racial_mods_basic():
    s = Stats(STR=10, DEX=10, CON=10, INT=10, WIS=10, CHA=10)
    out = apply_racial_mods(s, {"STR": 2, "CON": 1})
    assert out.STR == 12
    assert out.CON == 11
    assert out.DEX == 10


def test_apply_racial_mods_does_not_mutate_input():
    s = Stats(STR=10)
    apply_racial_mods(s, {"STR": 2})
    assert s.STR == 10


def test_human_racial_all_plus_one():
    s = Stats(STR=10, DEX=10, CON=10, INT=10, WIS=10, CHA=10)
    out = apply_racial_mods(s, {"STR": 1, "DEX": 1, "CON": 1, "INT": 1, "WIS": 1, "CHA": 1})
    for n in ("STR", "DEX", "CON", "INT", "WIS", "CHA"):
        assert out.get(n) == 11


# ── HP ──

def test_l1_hp_full_die_plus_con():
    # d10 hit die + CON mod 3 = 13
    assert compute_max_hp(10, 3, 1) == 13


def test_l1_hp_negative_con_clamps_to_1():
    # d4 + (-3) = 1
    assert compute_max_hp(4, -3, 1) == 1


def test_l2_hp_avg_per_level():
    # L1: 10+3=13. L2: +(5+1+3)=+9. = 22
    assert compute_max_hp(10, 3, 2) == 22


# ── AC ──

def test_ac_no_armor():
    # base 10 + DEX +2 = 12
    assert compute_ac(dex_modifier=2) == 12


def test_ac_chainmail_caps_dex():
    # chainmail base 16, max DEX 2; with DEX +4, only +2 counts
    assert compute_ac(dex_modifier=4, armor_base=16, armor_max_dex=2) == 18


def test_ac_plate_no_dex():
    # plate base 18, max DEX 0
    assert compute_ac(dex_modifier=4, armor_base=18, armor_max_dex=0) == 18


def test_ac_with_shield():
    assert compute_ac(dex_modifier=2, armor_base=16, armor_max_dex=2, shield_bonus=2) == 20


# ── Attack / saves / spell DC ──

def test_attack_bonus_proficient():
    # STR mod +3, prof +2 = +5
    assert attack_bonus(stat_mod=3, prof_bonus=2, proficient=True) == 5


def test_attack_bonus_not_proficient():
    assert attack_bonus(stat_mod=3, prof_bonus=2, proficient=False) == 3


def test_spell_save_dc():
    # 8 + prof 2 + caster +3 = 13
    assert spell_save_dc(prof_bonus=2, caster_mod=3) == 13


def test_spell_attack_bonus():
    assert spell_attack_bonus(prof_bonus=2, caster_mod=3) == 5


def test_save_bonus_proficient_and_not():
    assert save_bonus(stat_mod=3, prof_bonus=2, proficient=True) == 5
    assert save_bonus(stat_mod=3, prof_bonus=2, proficient=False) == 3


def test_initiative_bonus():
    assert initiative_bonus(dex_modifier=2) == 2
    assert initiative_bonus(dex_modifier=2, misc=1) == 3


# ── Stats helpers ──

def test_stats_get_set():
    s = Stats()
    s.set("str", 16)
    assert s.get("STR") == 16
    assert s.get("str") == 16


def test_stats_to_from_dict():
    s = Stats(STR=15, DEX=14, CON=13, INT=12, WIS=10, CHA=8)
    d = s.to_dict()
    s2 = Stats.from_dict(d)
    assert s2 == s
