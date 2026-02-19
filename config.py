import os

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

LLM_BACKEND = os.environ.get("LLM_BACKEND", "ollama")  # "anthropic" or "ollama"
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")

if LLM_BACKEND == "ollama":
    AGENT_MODEL = os.environ.get("AGENT_MODEL", "gemma3:4b")
    NARRATOR_MODEL = os.environ.get("NARRATOR_MODEL", "gemma3:4b")
else:
    AGENT_MODEL = os.environ.get("AGENT_MODEL", "claude-sonnet-4-20250514")
    NARRATOR_MODEL = os.environ.get("NARRATOR_MODEL", "claude-sonnet-4-20250514")

QUEST_DESCRIPTION = "Explore the dungeon with your allies. Talk to NPCs for lore and gifts, gear up with better equipment, and slay the final boss."

MAX_TICKS = 20
NUM_AGENTS = 3
ACTION_HISTORY_SIZE = 12  # rolling window of tactical events (combat, movement, items)
COMM_HISTORY_SIZE = 5     # rolling window of ally communications (tell, say, whisper, yell)
LORE_HISTORY_SIZE = 3     # rolling window of NPC dialogue summaries

# Combat constants
HEAL_PERCENT = 0.3
POISON_DURATION = 3
POISON_DAMAGE = 1

# Spell costs (legacy — kept for backwards compat, abilities.py uses ABILITY_DEFINITIONS)
SPELL_COSTS = {
    "missile": 1,
    "fireball": 3,
    "poison": 2,
    "heal": 2,
}

# Shared base personality for all agents
BASE_PERSONALITY = "Works with allies to survive and progress. Explores thoroughly to find better gear, defeats enemies for loot drops, talks to NPCs for gifts and intel, and coordinates with allies."

# ── Class Definitions ──────────────────────────────────────────────────
# Each class defines base stats, resource type, speed, abilities, and defaults.

CLASS_DEFINITIONS = {
    "Warrior": {
        "hp": 25,
        "resource_type": "ap",
        "resource_max": 10,
        "speed": 3,
        "abilities": ["attack", "cleave", "taunt", "defend", "rally"],
        "default_name": "Kael",
        "personality": "Aggressive and brave. Charges into battle first, protects allies.",
        "weapon": {"name": "Longsword", "slot": "weapon", "atk": 5, "pdef": 0, "mdef": 0, "mdmg": 0},
        "armor": {"name": "Chainmail", "slot": "armor", "atk": 0, "pdef": 3, "mdef": 0, "mdmg": 0},
        "ring": {"name": "Iron Band", "slot": "ring", "atk": 0, "pdef": 0, "mdef": 1, "mdmg": 1},
    },
    "Paladin": {
        "hp": 20,
        "resource_type": "mp",
        "resource_max": 8,
        "speed": 3,
        "abilities": ["attack", "smite", "lay_on_hands", "shield", "consecrate"],
        "default_name": "Aldric",
        "personality": "Righteous and steadfast. Heals and protects allies while smiting evil.",
        "weapon": {"name": "Warhammer", "slot": "weapon", "atk": 4, "pdef": 0, "mdef": 0, "mdmg": 0},
        "armor": {"name": "Plate Armor", "slot": "armor", "atk": 0, "pdef": 4, "mdef": 1, "mdmg": 0},
        "ring": {"name": "Holy Signet", "slot": "ring", "atk": 0, "pdef": 0, "mdef": 2, "mdmg": 2},
    },
    "Mage": {
        "hp": 8,
        "resource_type": "mp",
        "resource_max": 25,
        "speed": 4,
        "abilities": ["attack", "missile", "arcane_storm", "curse", "barrier"],
        "default_name": "Lyria",
        "personality": "Strategic and decisive. Wields devastating magic to clear enemies and support allies.",
        "weapon": {"name": "Oak Staff", "slot": "weapon", "atk": 2, "pdef": 0, "mdef": 0, "mdmg": 0},
        "armor": {"name": "Mage Robes", "slot": "armor", "atk": 0, "pdef": 1, "mdef": 3, "mdmg": 0},
        "ring": {"name": "Sapphire Focus", "slot": "ring", "atk": 0, "pdef": 0, "mdef": 2, "mdmg": 5},
    },
    "Cleric": {
        "hp": 14,
        "resource_type": "mp",
        "resource_max": 18,
        "speed": 3,
        "abilities": ["attack", "heal", "ward", "holy_bolt", "cure"],
        "default_name": "Sera",
        "personality": "Compassionate healer. Keeps allies alive and purges debuffs.",
        "weapon": {"name": "Mace", "slot": "weapon", "atk": 3, "pdef": 0, "mdef": 0, "mdmg": 0},
        "armor": {"name": "Chain Vestments", "slot": "armor", "atk": 0, "pdef": 2, "mdef": 2, "mdmg": 0},
        "ring": {"name": "Prayer Beads", "slot": "ring", "atk": 0, "pdef": 0, "mdef": 2, "mdmg": 4},
    },
    "Ranger": {
        "hp": 14,
        "resource_type": "mp",
        "resource_max": 10,
        "speed": 5,
        "abilities": ["attack", "aimed_shot", "volley", "poison_arrow", "sleep"],
        "default_name": "Finn",
        "personality": "Practical and observant. Scouts ahead, finds paths, reports back.",
        "weapon": {"name": "Hunting Bow", "slot": "weapon", "atk": 4, "pdef": 0, "mdef": 0, "mdmg": 0},
        "armor": {"name": "Leather Armor", "slot": "armor", "atk": 0, "pdef": 2, "mdef": 1, "mdmg": 0},
        "ring": {"name": "Emerald Charm", "slot": "ring", "atk": 0, "pdef": 0, "mdef": 1, "mdmg": 3},
    },
    "Rogue": {
        "hp": 12,
        "resource_type": "mp",
        "resource_max": 8,
        "speed": 6,
        "abilities": ["attack", "backstab", "bleed", "evade", "smoke_bomb"],
        "default_name": "Shade",
        "personality": "Cunning and elusive. Strikes from the shadows, disables enemies.",
        "weapon": {"name": "Twin Daggers", "slot": "weapon", "atk": 4, "pdef": 0, "mdef": 0, "mdmg": 0},
        "armor": {"name": "Shadow Cloak", "slot": "armor", "atk": 0, "pdef": 1, "mdef": 1, "mdmg": 0},
        "ring": {"name": "Venom Ring", "slot": "ring", "atk": 0, "pdef": 0, "mdef": 1, "mdmg": 2},
    },
}

# ── Ability Definitions ────────────────────────────────────────────────
# cost_type: "mp", "ap", "hp", or "free"
# target: "enemy", "self", "ally", "ally_or_self", "all_enemies", "all_allies"
# aoe: True if ability hits all targets of that type

ABILITY_DEFINITIONS = {
    # ── Warrior (AP-based) ──
    "attack":       {"cost": 0, "cost_type": "free", "target": "enemy", "aoe": False, "description": "Melee attack (weapon ATK)"},
    "cleave":       {"cost": 3, "cost_type": "ap", "target": "all_enemies", "aoe": True, "description": "Hit all enemies (weapon ATK, 3 AP)"},
    "taunt":        {"cost": 2, "cost_type": "ap", "target": "self", "aoe": False, "description": "Force all mobs to target you next turn (2 AP)"},
    "defend":       {"cost": 2, "cost_type": "ap", "target": "self", "aoe": False, "description": "Reduce incoming damage by 50% this tick (2 AP)"},
    "rally":        {"cost": 4, "cost_type": "ap", "target": "all_allies", "aoe": True, "description": "All allies deal +2 damage on next hit (4 AP)"},

    # ── Paladin (MP-based) ──
    "smite":        {"cost": 2, "cost_type": "mp", "target": "enemy", "aoe": False, "description": "Holy strike: ATK*1.5 vs MDEF (2 MP)"},
    "lay_on_hands": {"cost": 3, "cost_type": "mp", "target": "ally_or_self", "aoe": False, "description": "Restore 40% max HP (3 MP)"},
    "shield":       {"cost": 2, "cost_type": "mp", "target": "ally", "aoe": False, "description": "Redirect next attack on ally to you (2 MP)"},
    "consecrate":   {"cost": 4, "cost_type": "mp", "target": "all_enemies", "aoe": True, "description": "Holy AoE: ATK vs MDEF per mob (4 MP)"},

    # ── Mage (MP-based) ──
    "missile":      {"cost": 1, "cost_type": "mp", "target": "enemy", "aoe": False, "description": "Magic missile (ring MDMG vs MDEF, 1 MP)"},
    "arcane_storm": {"cost": 4, "cost_type": "mp", "target": "all_enemies", "aoe": True, "description": "AoE: MDMG*2 vs MDEF per mob (4 MP)"},
    "curse":        {"cost": 2, "cost_type": "mp", "target": "enemy", "aoe": False, "description": "2 dmg/tick for 3 ticks (2 MP)"},
    "barrier":      {"cost": 3, "cost_type": "mp", "target": "ally_or_self", "aoe": False, "description": "Absorb 8 damage on target (3 MP)"},

    # ── Cleric (MP-based) ──
    "heal":         {"cost": 2, "cost_type": "mp", "target": "ally_or_self", "aoe": False, "description": "Restore 30% max HP (2 MP)"},
    "ward":         {"cost": 2, "cost_type": "mp", "target": "ally_or_self", "aoe": False, "description": "Reduce damage by 3 for 3 ticks (2 MP)"},
    "holy_bolt":    {"cost": 2, "cost_type": "mp", "target": "enemy", "aoe": False, "description": "Holy bolt: MDMG*1.5 vs MDEF (2 MP)"},
    "cure":         {"cost": 1, "cost_type": "mp", "target": "ally_or_self", "aoe": False, "description": "Remove all debuffs (1 MP)"},

    # ── Ranger (MP-based) ──
    "aimed_shot":   {"cost": 3, "cost_type": "mp", "target": "enemy", "aoe": False, "description": "ATK*2 vs PDEF (3 MP)"},
    "volley":       {"cost": 3, "cost_type": "mp", "target": "all_enemies", "aoe": True, "description": "Hit all enemies (weapon ATK, 3 MP)"},
    "poison_arrow": {"cost": 2, "cost_type": "mp", "target": "enemy", "aoe": False, "description": "2 dmg/tick for 3 ticks (2 MP)"},
    "sleep":        {"cost": 3, "cost_type": "mp", "target": "enemy", "aoe": False, "description": "Target skips next 2 turns (3 MP)"},

    # ── Rogue (mixed HP/MP) ──
    "backstab":     {"cost": 3, "cost_type": "hp", "target": "enemy", "aoe": False, "description": "ATK*2.5, ignores defense (3 HP)"},
    "bleed":        {"cost": 2, "cost_type": "mp", "target": "enemy", "aoe": False, "description": "2 dmg/tick for 3 ticks (2 MP)"},
    "evade":        {"cost": 2, "cost_type": "hp", "target": "self", "aoe": False, "description": "Next attack deals 0 damage (2 HP)"},
    "smoke_bomb":   {"cost": 3, "cost_type": "mp", "target": "all_enemies", "aoe": True, "description": "All enemies deal -3 damage for 2 ticks (3 MP)"},
}


# Agent starting stats (legacy — kept for backwards compat with old create_agents)
AGENT_TEMPLATES = [
    {
        "name": "Kael",
        "personality": "Aggressive and brave. Charges into battle first, protects allies.",
        "agent_class": "Warrior",
        "hp": 25,
        "max_hp": 25,
        "mp": 10,
        "max_mp": 10,
        "weapon": {"name": "Longsword", "slot": "weapon", "atk": 5, "pdef": 0, "mdef": 0, "mdmg": 0},
        "armor": {"name": "Chainmail", "slot": "armor", "atk": 0, "pdef": 3, "mdef": 0, "mdmg": 0},
        "ring": {"name": "Iron Band", "slot": "ring", "atk": 0, "pdef": 0, "mdef": 1, "mdmg": 1},
    },
    {
        "name": "Lyria",
        "personality": "Strategic and decisive. Wields devastating magic to clear enemies and support allies.",
        "agent_class": "Mage",
        "hp": 8,
        "max_hp": 8,
        "mp": 25,
        "max_mp": 25,
        "weapon": {"name": "Oak Staff", "slot": "weapon", "atk": 2, "pdef": 0, "mdef": 0, "mdmg": 0},
        "armor": {"name": "Mage Robes", "slot": "armor", "atk": 0, "pdef": 1, "mdef": 3, "mdmg": 0},
        "ring": {"name": "Sapphire Focus", "slot": "ring", "atk": 0, "pdef": 0, "mdef": 2, "mdmg": 5},
    },
    {
        "name": "Finn",
        "personality": "Practical and observant. Scouts ahead, finds paths, reports back.",
        "agent_class": "Ranger",
        "hp": 14,
        "max_hp": 14,
        "mp": 10,
        "max_mp": 10,
        "weapon": {"name": "Hunting Bow", "slot": "weapon", "atk": 4, "pdef": 0, "mdef": 0, "mdmg": 0},
        "armor": {"name": "Leather Armor", "slot": "armor", "atk": 0, "pdef": 2, "mdef": 1, "mdmg": 0},
        "ring": {"name": "Emerald Charm", "slot": "ring", "atk": 0, "pdef": 0, "mdef": 1, "mdmg": 3},
    },
]
