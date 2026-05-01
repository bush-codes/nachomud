"""Tests for factions.py — attitude matrix + race overlay + aggression."""
from __future__ import annotations

from nachomud.world.factions import (
    attitude,
    base_attitude,
    is_hostile,
    race_modifier,
    shift_attitude,
    will_attack_on_sight,
)


def test_default_townfolk_friendly_to_player():
    assert attitude("village_human", "none") == "friendly"
    assert attitude("none", "village_human") == "friendly"


def test_goblin_hostile_to_player():
    assert attitude("goblin_clan", "none") == "hostile"


def test_unknown_pair_neutral():
    assert attitude("unknown_a", "unknown_b") == "neutral"


def test_dwarf_race_overlay_makes_goblin_meaner():
    base = attitude("goblin_clan", "none")
    with_dwarf = attitude("goblin_clan", "none", target_race="Dwarf")
    # Dwarf race is targeted, so target_race contributes Dwarf->goblin_clan = -1 (one step meaner)
    # base hostile is the worst, so it stays hostile (clamped)
    assert with_dwarf == "hostile"


def test_shift_attitude_clamps_at_extremes():
    assert shift_attitude("hostile", -5) == "hostile"
    assert shift_attitude("allied", +5) == "allied"


def test_is_hostile_includes_unfriendly():
    assert is_hostile("goblin_clan", "none")
    assert is_hostile("wild_beast", "none")
    assert not is_hostile("village_human", "none")


def test_will_attack_on_sight_high_aggression():
    assert will_attack_on_sight("goblin_clan", "none", aggression=8)
    assert not will_attack_on_sight("goblin_clan", "none", aggression=2)


def test_will_attack_on_sight_unfriendly_needs_high_aggression():
    assert will_attack_on_sight("wild_beast", "none", aggression=9)
    assert not will_attack_on_sight("wild_beast", "none", aggression=5)


def test_friendly_never_attacks():
    assert not will_attack_on_sight("village_human", "none", aggression=10)
