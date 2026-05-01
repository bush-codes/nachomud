"""Player classes: hit die, primary stat, save profs, abilities."""
from __future__ import annotations

# ── Class Definitions ──────────────────────────────────────────────────
# Each class defines hit die, primary stat, save proficiencies, caster mod,
# starting abilities, level-gated unlocks, and starting equipment.

CLASS_DEFINITIONS = {
    "Warrior": {
        "hit_die": 10,
        "primary_stat": "STR",
        "save_proficiencies": ["STR", "CON"],
        "caster_mod": None,
        "resource_type": "ap",
        "resource_max": 10,
        "speed": 3,
        "abilities": ["attack", "cleave", "taunt", "defend", "rally"],
        "starting_abilities": ["attack", "defend"],
        "ability_unlocks": {3: "taunt", 5: "cleave", 7: "rally"},
        "default_name": "Kael",
        "weapon": {
            "name": "Longsword", "slot": "weapon",
            "damage_die": "1d8", "damage_type": "slashing", "versatile_die": "1d10",
            "atk": 5,  # legacy
        },
        "armor": {
            "name": "Chainmail", "slot": "armor",
            "armor_base": 16, "armor_max_dex": 2,
            "pdef": 3,  # legacy
        },
        "ring": {
            "name": "Iron Band", "slot": "ring",
            "save_bonus": 1,
            "mdef": 1, "mdmg": 1,  # legacy
        },
    },
    "Paladin": {
        "hit_die": 8,
        "primary_stat": "STR",
        "save_proficiencies": ["WIS", "CHA"],
        "caster_mod": "CHA",
        "resource_type": "mp",
        "resource_max": 8,
        "speed": 3,
        "abilities": ["attack", "smite", "lay_on_hands", "shield", "consecrate"],
        "starting_abilities": ["attack", "shield"],
        "ability_unlocks": {3: "smite", 5: "lay_on_hands", 7: "consecrate"},
        "default_name": "Aldric",
        "weapon": {
            "name": "Warhammer", "slot": "weapon",
            "damage_die": "1d8", "damage_type": "bludgeoning", "versatile_die": "1d10",
            "atk": 4,  # legacy
        },
        "armor": {
            "name": "Plate Armor", "slot": "armor",
            "armor_base": 18, "armor_max_dex": 0,
            "pdef": 4, "mdef": 1,  # legacy
        },
        "ring": {
            "name": "Holy Signet", "slot": "ring",
            "spell_dc_bonus": 0, "save_bonus": 1,
            "mdef": 2, "mdmg": 2,  # legacy
        },
    },
    "Mage": {
        "hit_die": 4,
        "primary_stat": "INT",
        "save_proficiencies": ["INT", "WIS"],
        "caster_mod": "INT",
        "resource_type": "mp",
        "resource_max": 25,
        "speed": 4,
        "abilities": ["attack", "missile", "arcane_storm", "curse", "barrier"],
        "starting_abilities": ["attack", "missile"],
        "ability_unlocks": {3: "barrier", 5: "curse", 7: "arcane_storm"},
        "default_name": "Lyria",
        "weapon": {
            "name": "Oak Staff", "slot": "weapon",
            "damage_die": "1d6", "damage_type": "bludgeoning", "is_two_handed": True,
            "atk": 2,  # legacy
        },
        "armor": {
            "name": "Mage Robes", "slot": "armor",
            "armor_base": 11, "armor_max_dex": None,
            "pdef": 1, "mdef": 3,  # legacy
        },
        "ring": {
            "name": "Sapphire Focus", "slot": "ring",
            "spell_attack_bonus": 1, "spell_dc_bonus": 1,
            "mdef": 2, "mdmg": 5,  # legacy
        },
    },
    "Cleric": {
        "hit_die": 8,
        "primary_stat": "WIS",
        "save_proficiencies": ["WIS", "CHA"],
        "caster_mod": "WIS",
        "resource_type": "mp",
        "resource_max": 18,
        "speed": 3,
        "abilities": ["attack", "heal", "ward", "holy_bolt", "cure"],
        "starting_abilities": ["attack", "heal"],
        "ability_unlocks": {3: "ward", 5: "holy_bolt", 7: "cure"},
        "default_name": "Sera",
        "weapon": {
            "name": "Mace", "slot": "weapon",
            "damage_die": "1d6", "damage_type": "bludgeoning",
            "atk": 3,  # legacy
        },
        "armor": {
            "name": "Chain Vestments", "slot": "armor",
            "armor_base": 14, "armor_max_dex": 2,
            "pdef": 2, "mdef": 2,  # legacy
        },
        "ring": {
            "name": "Prayer Beads", "slot": "ring",
            "spell_dc_bonus": 1,
            "mdef": 2, "mdmg": 4,  # legacy
        },
    },
    "Ranger": {
        "hit_die": 8,
        "primary_stat": "DEX",
        "save_proficiencies": ["STR", "DEX"],
        "caster_mod": "WIS",
        "resource_type": "mp",
        "resource_max": 10,
        "speed": 5,
        "abilities": ["attack", "aimed_shot", "volley", "poison_arrow", "sleep"],
        "starting_abilities": ["attack", "aimed_shot"],
        "ability_unlocks": {3: "poison_arrow", 5: "volley", 7: "sleep"},
        "default_name": "Finn",
        "weapon": {
            "name": "Hunting Bow", "slot": "weapon",
            "damage_die": "1d8", "damage_type": "piercing", "ranged": True, "is_two_handed": True,
            "atk": 4,  # legacy
        },
        "armor": {
            "name": "Leather Armor", "slot": "armor",
            "armor_base": 11, "armor_max_dex": None,
            "pdef": 2, "mdef": 1,  # legacy
        },
        "ring": {
            "name": "Emerald Charm", "slot": "ring",
            "save_bonus": 1,
            "mdef": 1, "mdmg": 3,  # legacy
        },
    },
    "Rogue": {
        "hit_die": 6,
        "primary_stat": "DEX",
        "save_proficiencies": ["DEX", "INT"],
        "caster_mod": None,
        "resource_type": "mp",
        "resource_max": 8,
        "speed": 6,
        "abilities": ["attack", "backstab", "bleed", "evade", "smoke_bomb"],
        "starting_abilities": ["attack", "backstab"],
        "ability_unlocks": {3: "evade", 5: "bleed", 7: "smoke_bomb"},
        "default_name": "Shade",
        "weapon": {
            "name": "Twin Daggers", "slot": "weapon",
            "damage_die": "1d4", "damage_type": "piercing", "finesse": True,
            "atk": 4,  # legacy
        },
        "armor": {
            "name": "Shadow Cloak", "slot": "armor",
            "armor_base": 11, "armor_max_dex": None,
            "pdef": 1, "mdef": 1,  # legacy
        },
        "ring": {
            "name": "Venom Ring", "slot": "ring",
            "damage_bonus": 1,
            "mdef": 1, "mdmg": 2,  # legacy
        },
    },
}
