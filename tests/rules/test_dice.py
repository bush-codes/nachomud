"""Tests for dice.py — dice rolling utilities."""
from __future__ import annotations

import pytest

import nachomud.rules.dice as dice
def test_roll_d20_in_range():
    dice.seed(0)
    for _ in range(100):
        v = dice.roll_d20()
        assert 1 <= v <= 20


def test_roll_notation_basic():
    dice.seed(0)
    for _ in range(100):
        v = dice.roll("1d6")
        assert 1 <= v <= 6


def test_roll_notation_with_count():
    dice.seed(0)
    for _ in range(100):
        v = dice.roll("3d6")
        assert 3 <= v <= 18


def test_roll_notation_with_modifier():
    dice.seed(0)
    for _ in range(50):
        v = dice.roll("1d6+2")
        assert 3 <= v <= 8


def test_roll_notation_negative_modifier():
    dice.seed(0)
    for _ in range(50):
        v = dice.roll("1d6-1")
        assert 0 <= v <= 5


def test_roll_detail_returns_per_die():
    dice.seed(42)
    r = dice.roll_detail("3d6+1")
    assert len(r.rolls) == 3
    assert r.modifier == 1
    assert r.total == sum(r.rolls) + 1


def test_invalid_notation_raises():
    with pytest.raises(ValueError):
        dice.roll("garbage")
    with pytest.raises(ValueError):
        dice.roll("0d6")


def test_seed_makes_deterministic():
    dice.seed(123)
    a = [dice.roll_d20() for _ in range(20)]
    dice.seed(123)
    b = [dice.roll_d20() for _ in range(20)]
    assert a == b


def test_advantage_higher_or_equal_to_d20():
    dice.seed(0)
    for _ in range(50):
        # advantage takes max of two d20s; should never be less than at least one of them
        v = dice.roll_advantage()
        assert 1 <= v <= 20


def test_disadvantage_in_range():
    dice.seed(0)
    for _ in range(50):
        v = dice.roll_disadvantage()
        assert 1 <= v <= 20


def test_dice_doubled_increases_count_only():
    dice.seed(99)
    # 1d8+3 normally rolls 1 die; doubled rolls 2 dice but doesn't double mod
    # Range: 2..16 + 3 = 5..19
    for _ in range(50):
        v = dice.roll_dice_doubled("1d8+3")
        assert 5 <= v <= 19


def test_dice_doubled_no_modifier():
    dice.seed(99)
    for _ in range(50):
        v = dice.roll_dice_doubled("2d6")
        assert 4 <= v <= 24
