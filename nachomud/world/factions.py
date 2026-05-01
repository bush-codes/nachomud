"""Faction system: who attacks whom, modulated by race attitudes and per-mob
aggression. Factions are strings (no enum) so DM-generated content can mint
new factions on the fly without code changes — unknown factions default to
neutral against everything.
"""
from __future__ import annotations

from typing import Literal

Attitude = Literal["hostile", "unfriendly", "neutral", "friendly", "allied"]
ATTITUDE_ORDER = ["hostile", "unfriendly", "neutral", "friendly", "allied"]
# Indices: hostile=0 (worst) ... allied=4 (best). +1 step = nicer.


# ── Default matrix ──
# (factionA, factionB) → Attitude. Symmetric by default; missing pairs are neutral.

_DEFAULT_MATRIX: dict[tuple[str, str], Attitude] = {
    # Townsfolk are friendly to "none" (the unaffiliated player)
    ("village_human", "none"): "friendly",
    ("none", "village_human"): "friendly",

    # Goblin clans hate humans
    ("village_human", "goblin_clan"): "hostile",
    ("goblin_clan", "village_human"): "hostile",
    ("village_human", "ash_goblin_clan"): "hostile",
    ("ash_goblin_clan", "village_human"): "hostile",
    ("goblin_clan", "none"): "hostile",
    ("ash_goblin_clan", "none"): "hostile",

    # Wild beasts are unpredictable
    ("village_human", "wild_beast"): "unfriendly",
    ("wild_beast", "village_human"): "unfriendly",
    ("wild_beast", "none"): "unfriendly",

    # Undead and void hate everything alive
    ("undead", "none"): "hostile",
    ("undead", "village_human"): "hostile",
    ("village_human", "undead"): "hostile",
    ("none", "undead"): "hostile",
    ("void", "none"): "hostile",
    ("none", "void"): "hostile",
    ("void", "village_human"): "hostile",
    ("village_human", "void"): "hostile",

    # Goblin clans tolerate other goblin clans (uneasy alliance)
    ("goblin_clan", "ash_goblin_clan"): "neutral",
    ("ash_goblin_clan", "goblin_clan"): "neutral",
}


# ── Race attitude overlay (modifier in attitude steps; +1 = one step nicer) ──
# Symmetric by convention. Missing entries are 0.

_RACE_MODS: dict[tuple[str, str], int] = {
    ("Dwarf", "goblin_clan"): -1,
    ("Dwarf", "ash_goblin_clan"): -1,
    ("Elf", "goblin_clan"): -1,
    ("Elf", "ash_goblin_clan"): -1,
    ("Half-Orc", "village_human"): -1,
    ("Half-Orc", "goblin_clan"): +1,  # Orcs and goblins less likely to attack each other
}


def base_attitude(actor_faction: str, target_faction: str) -> Attitude:
    return _DEFAULT_MATRIX.get((actor_faction, target_faction), "neutral")


def race_modifier(actor_race: str | None, target_faction: str) -> int:
    if not actor_race:
        return 0
    return _RACE_MODS.get((actor_race, target_faction), 0)


def shift_attitude(att: Attitude, delta: int) -> Attitude:
    """Move attitude up (+1 = nicer) or down (-1 = meaner) by N steps."""
    idx = ATTITUDE_ORDER.index(att)
    new_idx = max(0, min(len(ATTITUDE_ORDER) - 1, idx + delta))
    return ATTITUDE_ORDER[new_idx]


def attitude(
    actor_faction: str, target_faction: str,
    actor_race: str | None = None, target_race: str | None = None,
) -> Attitude:
    """Effective attitude of `actor` toward `target`."""
    att = base_attitude(actor_faction, target_faction)
    # Race overlays apply when actor_race targets target_faction (and vice versa)
    delta = race_modifier(actor_race, target_faction)
    if target_race:
        delta += race_modifier(target_race, actor_faction)
    return shift_attitude(att, delta)


def is_hostile(actor_faction: str, target_faction: str,
               actor_race: str | None = None, target_race: str | None = None) -> bool:
    return attitude(actor_faction, target_faction, actor_race, target_race) in ("hostile", "unfriendly")


def will_attack_on_sight(mob_faction: str, target_faction: str, aggression: int,
                         actor_race: str | None = None, target_race: str | None = None) -> bool:
    """Decide whether a mob will initiate combat on seeing the target.

    aggression 0..10 maps to how readily the mob acts on hostility:
      hostile + aggression>=5 → attacks
      hostile + aggression<5  → grumbles
      unfriendly + aggression>=8 → attacks
      neutral/friendly/allied → never initiates
    """
    att = attitude(mob_faction, target_faction, actor_race, target_race)
    if att == "hostile":
        return aggression >= 5
    if att == "unfriendly":
        return aggression >= 8
    return False
