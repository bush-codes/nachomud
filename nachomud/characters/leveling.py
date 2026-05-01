"""Leveling: detect XP threshold crossings, apply level-up effects.

5e-flavored:
- Level threshold table from config.XP_TO_LEVEL.
- HP gain per level: hit_die avg + CON mod.
- Proficiency bonus auto-recomputed via stats.proficiency_bonus().
- Ability unlocks at L3/L5/L7 from class definition.
- Stat increase at L4 (and L8 in 5e proper) — for v1, auto-applies +2 to
  the class primary stat. Future polish can prompt the player.

The level-up runs idempotently: if the player crosses multiple thresholds
in one go (big XP haul), it walks them up one level at a time.
"""
from __future__ import annotations

from dataclasses import dataclass

from nachomud.rules.classes import CLASS_DEFINITIONS
from nachomud.rules.leveling import MAX_LEVEL, XP_TO_LEVEL
from nachomud.models import AgentState
from nachomud.rules.stats import compute_max_hp, mod, proficiency_bonus


@dataclass
class LevelUp:
    new_level: int
    hp_gained: int
    new_max_hp: int
    new_prof_bonus: int
    abilities_unlocked: list[str]
    stat_increase: tuple[str, int] | None  # (stat, amount) if applied this level


def xp_to_next_level(player: AgentState) -> int:
    """How much XP until the next level (∞ if at max level)."""
    if player.level >= MAX_LEVEL:
        return 10**9
    next_threshold = XP_TO_LEVEL.get(player.level + 1)
    if next_threshold is None:
        return 10**9
    return max(0, next_threshold - player.xp)


def can_level_up(player: AgentState) -> bool:
    if player.level >= MAX_LEVEL:
        return False
    nxt = XP_TO_LEVEL.get(player.level + 1)
    return nxt is not None and player.xp >= nxt


def apply_one_level_up(player: AgentState) -> LevelUp:
    """Bump the player by exactly one level. Caller must verify can_level_up()."""
    if not can_level_up(player):
        raise RuntimeError("not enough XP to level up")

    class_def = CLASS_DEFINITIONS.get(player.agent_class)
    if not class_def:
        raise RuntimeError(f"unknown class: {player.agent_class}")

    new_level = player.level + 1
    player.level = new_level
    new_prof = proficiency_bonus(new_level)
    player.proficiency_bonus = new_prof

    # Stat increase at L4 (5e standard ASI). v1: +2 to primary stat. Cap at 20.
    stat_increase: tuple[str, int] | None = None
    if new_level == 4:
        primary = class_def["primary_stat"]
        cur = player.stats.get(primary, 10)
        new_val = min(20, cur + 2)
        if new_val > cur:
            player.stats[primary] = new_val
            stat_increase = (primary, new_val - cur)

    # Recompute max HP from class hit die + CON mod at the new level
    con_mod = mod(player.stats.get("CON", 10))
    new_max_hp = compute_max_hp(class_def["hit_die"], con_mod, new_level)
    hp_gained = new_max_hp - player.max_hp
    player.max_hp = new_max_hp
    # Heal the gained HP (you also get back to full HP on level up — generous, but
    # keeps the post-grind moment satisfying)
    player.hp = new_max_hp

    # Ability unlocks
    unlocks = class_def.get("ability_unlocks", {})
    new_abilities: list[str] = []
    for unlock_level, ability in unlocks.items():
        if int(unlock_level) == new_level and ability not in player.abilities:
            player.abilities.append(ability)
            new_abilities.append(ability)

    return LevelUp(
        new_level=new_level,
        hp_gained=hp_gained,
        new_max_hp=new_max_hp,
        new_prof_bonus=new_prof,
        abilities_unlocked=new_abilities,
        stat_increase=stat_increase,
    )


def apply_all_pending_level_ups(player: AgentState) -> list[LevelUp]:
    """Walk the player up through any pending level thresholds. Returns each step."""
    out: list[LevelUp] = []
    while can_level_up(player):
        out.append(apply_one_level_up(player))
    return out


def render_level_up(lu: LevelUp, player_name: str) -> str:
    """Build a short human-readable summary of what changed."""
    lines = [f"⭐ {player_name} reaches Level {lu.new_level}!"]
    if lu.hp_gained > 0:
        lines.append(f"  HP +{lu.hp_gained} (now {lu.new_max_hp})")
    if lu.new_prof_bonus > 2:
        lines.append(f"  Proficiency bonus: +{lu.new_prof_bonus}")
    if lu.stat_increase:
        s, amt = lu.stat_increase
        lines.append(f"  {s} +{amt}")
    if lu.abilities_unlocked:
        lines.append(f"  New ability: {', '.join(lu.abilities_unlocked)}")
    return "\n".join(lines)
