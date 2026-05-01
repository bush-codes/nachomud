"""Dice rolling utilities for D&D 5e-style mechanics.

Supports standard dice notation (`"1d20+5"`, `"2d6"`, `"1d8-1"`).
A configurable RNG seed is exposed for deterministic tests.
"""
from __future__ import annotations

import random
import re
from dataclasses import dataclass

_NOTATION = re.compile(r"^\s*(\d+)?\s*d\s*(\d+)\s*([+-]\s*\d+)?\s*$", re.IGNORECASE)
_rng = random.Random()


def seed(value: int | None) -> None:
    """Seed the dice RNG. Pass None to reseed from system entropy."""
    global _rng
    _rng = random.Random(value)


@dataclass
class Roll:
    notation: str
    rolls: list[int]
    modifier: int

    @property
    def total(self) -> int:
        return sum(self.rolls) + self.modifier

    def __repr__(self) -> str:
        return f"Roll({self.notation}: {self.rolls} + {self.modifier} = {self.total})"


def roll(notation: str) -> int:
    """Roll dice from notation, return total. `1d20+5`, `2d6`, `1d8-1`."""
    return roll_detail(notation).total


def roll_detail(notation: str) -> Roll:
    """Roll dice and return per-die values plus modifier."""
    m = _NOTATION.match(notation)
    if not m:
        raise ValueError(f"Invalid dice notation: {notation!r}")
    count = int(m.group(1) or "1")
    sides = int(m.group(2))
    mod_str = (m.group(3) or "").replace(" ", "")
    modifier = int(mod_str) if mod_str else 0
    if count <= 0 or sides <= 0:
        raise ValueError(f"Dice count and sides must be positive: {notation!r}")
    rolls = [_rng.randint(1, sides) for _ in range(count)]
    return Roll(notation=notation, rolls=rolls, modifier=modifier)


def roll_d20() -> int:
    return _rng.randint(1, 20)


def roll_advantage() -> int:
    """Roll 2d20 take higher (D&D advantage)."""
    return max(_rng.randint(1, 20), _rng.randint(1, 20))


def roll_disadvantage() -> int:
    """Roll 2d20 take lower (D&D disadvantage)."""
    return min(_rng.randint(1, 20), _rng.randint(1, 20))


def random_chance(p: float) -> bool:
    """Return True with probability p (0..1). Uses the same seeded RNG."""
    return _rng.random() < p


def random_choice(items):
    """Return one item at random. Uses the same seeded RNG."""
    return _rng.choice(items)


def roll_dice_doubled(notation: str) -> int:
    """Roll dice with doubled count (for crits). Modifier is NOT doubled — 5e rule."""
    m = _NOTATION.match(notation)
    if not m:
        raise ValueError(f"Invalid dice notation: {notation!r}")
    count = int(m.group(1) or "1") * 2
    sides = int(m.group(2))
    mod_str = (m.group(3) or "").replace(" ", "")
    modifier = int(mod_str) if mod_str else 0
    return sum(_rng.randint(1, sides) for _ in range(count)) + modifier
