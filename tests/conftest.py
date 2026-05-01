"""Shared test fixtures for NachoMUD tests."""
from __future__ import annotations

from unittest.mock import patch

import pytest

import nachomud.rules.dice as dice
from nachomud.characters.character import create_character
from nachomud.models import AgentState, GameEvent, Item, Mob, NPC, Room, StatusEffect
from nachomud.rules.stats import Stats


@pytest.fixture(autouse=True)
def deterministic_dice():
    """Seed the dice RNG so tests are deterministic."""
    dice.seed(0xC001D00D)
    yield
    dice.seed(None)


@pytest.fixture
def mock_llm():
    """Patch llm.chat to return a canned response (avoids real LLM calls)."""
    with patch("llm.chat", return_value="Think: test\nDo: attack Goblin") as m:
        yield m


# ── Player-style fixtures (built via create_character with standard stats) ──

@pytest.fixture
def mock_agent() -> AgentState:
    """L1 Human Warrior named Kael at room_1."""
    stats = Stats(STR=15, DEX=12, CON=14, INT=8, WIS=10, CHA=13)
    a = create_character("Kael", "Human", "Warrior", stats)
    a.room_id = "room_1"
    a.abilities = ["attack", "cleave", "taunt", "defend", "rally"]  # all unlocked for tests
    return a


@pytest.fixture
def mock_mage() -> AgentState:
    """L1 Human Mage named Lyria at room_1."""
    stats = Stats(STR=8, DEX=14, CON=12, INT=15, WIS=13, CHA=10)
    a = create_character("Lyria", "Human", "Mage", stats)
    a.room_id = "room_1"
    a.abilities = ["attack", "missile", "arcane_storm", "curse", "barrier"]
    return a


@pytest.fixture
def mock_paladin() -> AgentState:
    stats = Stats(STR=15, DEX=10, CON=13, INT=8, WIS=12, CHA=14)
    a = create_character("Aldric", "Human", "Paladin", stats)
    a.room_id = "room_1"
    a.abilities = ["attack", "smite", "lay_on_hands", "shield", "consecrate"]
    return a


@pytest.fixture
def mock_cleric() -> AgentState:
    stats = Stats(STR=10, DEX=12, CON=14, INT=8, WIS=15, CHA=13)
    a = create_character("Sera", "Human", "Cleric", stats)
    a.room_id = "room_1"
    a.abilities = ["attack", "heal", "ward", "holy_bolt", "cure"]
    return a


@pytest.fixture
def mock_ranger() -> AgentState:
    stats = Stats(STR=12, DEX=15, CON=13, INT=8, WIS=14, CHA=10)
    a = create_character("Finn", "Human", "Ranger", stats)
    a.room_id = "room_1"
    a.abilities = ["attack", "aimed_shot", "volley", "poison_arrow", "sleep"]
    return a


@pytest.fixture
def mock_rogue() -> AgentState:
    stats = Stats(STR=8, DEX=15, CON=14, INT=13, WIS=10, CHA=12)
    a = create_character("Shade", "Human", "Rogue", stats)
    a.room_id = "room_1"
    a.abilities = ["attack", "backstab", "bleed", "evade", "smoke_bomb"]
    return a


# ── Mob fixtures ──

@pytest.fixture
def mock_mob() -> Mob:
    """A Goblin Scout: low AC, low HP, weak."""
    return Mob(
        name="Goblin Scout", hp=8, max_hp=8, atk=2, ac=11, level=1,
        stats={"STR": 8, "DEX": 14, "CON": 10, "INT": 8, "WIS": 8, "CHA": 6},
        damage_die="1d4", damage_bonus=2,
        faction="goblin_clan", aggression=6,
    )


@pytest.fixture
def mock_boss() -> Mob:
    return Mob(
        name="Void Lord", hp=80, max_hp=80, atk=6, ac=17, mdef=2, is_boss=True, level=10,
        stats={"STR": 18, "DEX": 12, "CON": 18, "INT": 16, "WIS": 14, "CHA": 16},
        damage_die="2d6", damage_bonus=4,
        faction="void", aggression=10, proficiency_bonus=4,
    )


# ── NPC / Room fixtures ──

@pytest.fixture
def mock_npc() -> NPC:
    return NPC(
        name="Marcus",
        title="Wounded Soldier",
        dialogue=["warns about shadows"],
        interactions_left=2,
    )


@pytest.fixture
def mock_room(mock_mob) -> Room:
    return Room(
        id="room_1",
        name="Entry Chamber",
        description="A dark chamber.",
        exits={"n": "room_2"},
        mobs=[mock_mob],
    )


@pytest.fixture
def mock_room_empty() -> Room:
    return Room(
        id="room_2",
        name="Guard Barracks",
        description="Empty barracks.",
        exits={"s": "room_1", "n": "room_3"},
    )


@pytest.fixture
def mock_rooms(mock_room, mock_room_empty) -> dict[str, Room]:
    return {
        "room_1": mock_room,
        "room_2": mock_room_empty,
    }


# ── Legacy item fixtures (some tests still build their own characters) ──

@pytest.fixture
def basic_weapon() -> Item:
    return Item(name="Longsword", slot="weapon", damage_die="1d8", atk=5)


@pytest.fixture
def basic_armor() -> Item:
    return Item(name="Chainmail", slot="armor", armor_base=16, armor_max_dex=2, pdef=3)


@pytest.fixture
def basic_ring() -> Item:
    return Item(name="Iron Band", slot="ring", mdmg=1, mdef=1)
