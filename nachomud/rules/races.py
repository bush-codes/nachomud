"""Player races: stat modifiers + signature trait per race."""
from __future__ import annotations

# ── Race Definitions ───────────────────────────────────────────────────
# Each race defines stat modifiers (applied to point-buy result) and a trait.

RACE_DEFINITIONS = {
    "Human": {
        "stat_mods": {"STR": 1, "DEX": 1, "CON": 1, "INT": 1, "WIS": 1, "CHA": 1},
        "trait": "Versatile",
        "trait_description": "+1 to every ability score.",
    },
    "Dwarf": {
        "stat_mods": {"CON": 2, "STR": 1},
        "trait": "Stout",
        "trait_description": "Darkvision and resistance to poison damage.",
    },
    "Elf": {
        "stat_mods": {"DEX": 2, "INT": 1},
        "trait": "Fey Ancestry",
        "trait_description": "Darkvision and immunity to magical sleep.",
    },
    "Halfling": {
        "stat_mods": {"DEX": 2, "CHA": 1},
        "trait": "Lucky",
        "trait_description": "Once per short rest, reroll a natural 1.",
    },
    "Half-Orc": {
        "stat_mods": {"STR": 2, "CON": 1},
        "trait": "Relentless Endurance",
        "trait_description": "Once per long rest, drop to 1 HP instead of 0.",
    },
}

