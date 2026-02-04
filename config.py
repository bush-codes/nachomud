import os

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

NARRATOR_MODEL = "claude-sonnet-4-20250514"
AGENT_MODEL = "claude-sonnet-4-20250514"

MAX_TICKS = 50
NUM_AGENTS = 3

# Combat constants
HEAL_PERCENT = 0.3
POISON_DURATION = 3
POISON_DAMAGE = 1

# Spell costs
SPELL_COSTS = {
    "missile": 1,
    "fireball": 3,
    "poison": 2,
    "heal": 2,
}

# Agent starting stats
AGENT_TEMPLATES = [
    {
        "name": "Kael",
        "personality": "Aggressive and brave. Charges into battle first, protects allies. Speaks boldly.",
        "agent_class": "Warrior",
        "hp": 15,
        "max_hp": 15,
        "mp": 5,
        "max_mp": 5,
        "weapon": {"name": "Longsword", "slot": "weapon", "atk": 5, "pdef": 0, "mdef": 0, "mdmg": 0},
        "armor": {"name": "Chainmail", "slot": "armor", "atk": 0, "pdef": 3, "mdef": 0, "mdmg": 0},
        "ring": {"name": "Iron Band", "slot": "ring", "atk": 0, "pdef": 0, "mdef": 1, "mdmg": 1},
    },
    {
        "name": "Lyria",
        "personality": "Cautious and tactical. Prefers magic over melee. Analyzes situations before acting. Speaks thoughtfully.",
        "agent_class": "Mage",
        "hp": 8,
        "max_hp": 8,
        "mp": 15,
        "max_mp": 15,
        "weapon": {"name": "Oak Staff", "slot": "weapon", "atk": 2, "pdef": 0, "mdef": 0, "mdmg": 0},
        "armor": {"name": "Mage Robes", "slot": "armor", "atk": 0, "pdef": 1, "mdef": 3, "mdmg": 0},
        "ring": {"name": "Sapphire Focus", "slot": "ring", "atk": 0, "pdef": 0, "mdef": 2, "mdmg": 5},
    },
    {
        "name": "Finn",
        "personality": "Practical and observant. Scouts ahead, reports back. Good at finding paths and avoiding danger. Speaks plainly.",
        "agent_class": "Ranger",
        "hp": 12,
        "max_hp": 12,
        "mp": 8,
        "max_mp": 8,
        "weapon": {"name": "Hunting Bow", "slot": "weapon", "atk": 4, "pdef": 0, "mdef": 0, "mdmg": 0},
        "armor": {"name": "Leather Armor", "slot": "armor", "atk": 0, "pdef": 2, "mdef": 1, "mdmg": 0},
        "ring": {"name": "Emerald Charm", "slot": "ring", "atk": 0, "pdef": 0, "mdef": 1, "mdmg": 3},
    },
]

# Memory settings
MAX_MEMORY_ENTRIES = 20
MEMORY_DIR = "data/memories"
