"""D&D 5e stats system: Stats dataclass, point-buy validation, racial mods,
and derived value computations (HP, AC, attack bonus, prof bonus, spell DC).
"""
from __future__ import annotations

from dataclasses import dataclass, asdict

# 5e standard point-buy: 27 points, base 8 in each, max 15 before racial mods
POINT_BUY_BUDGET = 27
POINT_BUY_MIN = 8
POINT_BUY_MAX = 15
POINT_BUY_COSTS = {
    8: 0, 9: 1, 10: 2, 11: 3, 12: 4, 13: 5, 14: 7, 15: 9,
}

STAT_NAMES = ("STR", "DEX", "CON", "INT", "WIS", "CHA")


@dataclass
class Stats:
    STR: int = 10
    DEX: int = 10
    CON: int = 10
    INT: int = 10
    WIS: int = 10
    CHA: int = 10

    def get(self, name: str) -> int:
        return getattr(self, name.upper())

    def set(self, name: str, value: int) -> None:
        setattr(self, name.upper(), value)

    def to_dict(self) -> dict[str, int]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, int]) -> Stats:
        return cls(**{k.upper(): v for k, v in d.items() if k.upper() in STAT_NAMES})


def mod(stat: int) -> int:
    """5e ability modifier: (stat - 10) // 2, with floor for odd negatives."""
    # Python floor division naturally handles negatives correctly: (8 - 10) // 2 == -1
    return (stat - 10) // 2


def proficiency_bonus(level: int) -> int:
    """5e prof bonus: +2 at L1-4, +3 at L5-8, +4 at L9-12, +5 at L13-16, +6 at L17+."""
    return 2 + max(0, level - 1) // 4


def validate_point_buy(stats: Stats) -> tuple[bool, str]:
    """Validate stats against 5e 27-point buy. Returns (ok, reason)."""
    total = 0
    for name in STAT_NAMES:
        s = stats.get(name)
        if s < POINT_BUY_MIN or s > POINT_BUY_MAX:
            return False, f"{name}={s} out of range [{POINT_BUY_MIN}, {POINT_BUY_MAX}]"
        total += POINT_BUY_COSTS[s]
    if total > POINT_BUY_BUDGET:
        return False, f"Spent {total} points, budget is {POINT_BUY_BUDGET}"
    return True, ""


def point_buy_cost(stats: Stats) -> int:
    return sum(POINT_BUY_COSTS[stats.get(n)] for n in STAT_NAMES)


def apply_racial_mods(stats: Stats, mods: dict[str, int]) -> Stats:
    """Return new Stats with racial modifiers applied. `mods` like {"STR": 2, "CON": 1}."""
    new = Stats(**stats.to_dict())
    for stat_name, delta in mods.items():
        new.set(stat_name, new.get(stat_name) + delta)
    return new


# ── Derived values ──

def compute_max_hp(hit_die: int, con_modifier: int, level: int) -> int:
    """L1 = max die + con_mod. Subsequent levels = (die_avg + 1) + con_mod (5e take-average rule)."""
    if level < 1:
        return 0
    base = hit_die + con_modifier
    if level == 1:
        return max(1, base)
    avg_per_level = (hit_die // 2) + 1 + con_modifier
    return max(1, base + (level - 1) * avg_per_level)


def compute_ac(dex_modifier: int, armor_base: int = 10, armor_max_dex: int | None = None,
               shield_bonus: int = 0, misc_bonus: int = 0) -> int:
    """AC = armor_base + min(dex_mod, armor_max_dex if set) + shield + misc.

    armor_base=10 means "no armor" (the 10 includes the natural base).
    Heavy armor: armor_max_dex=0. Medium: 2. Light: None (full DEX).
    """
    if armor_max_dex is None:
        dex_contrib = dex_modifier
    else:
        dex_contrib = min(dex_modifier, armor_max_dex)
    return armor_base + dex_contrib + shield_bonus + misc_bonus


def attack_bonus(stat_mod: int, prof_bonus: int, proficient: bool = True, misc: int = 0) -> int:
    return stat_mod + (prof_bonus if proficient else 0) + misc


def spell_save_dc(prof_bonus: int, caster_mod: int, misc: int = 0) -> int:
    return 8 + prof_bonus + caster_mod + misc


def spell_attack_bonus(prof_bonus: int, caster_mod: int, misc: int = 0) -> int:
    return prof_bonus + caster_mod + misc


def save_bonus(stat_mod: int, prof_bonus: int, proficient: bool = False) -> int:
    return stat_mod + (prof_bonus if proficient else 0)


def initiative_bonus(dex_modifier: int, misc: int = 0) -> int:
    return dex_modifier + misc
