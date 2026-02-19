"""Shared test fixtures for NachoMUD tests."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from models import AgentState, GameEvent, Item, Mob, NPC, Room, StatusEffect


@pytest.fixture
def mock_llm():
    """Patch llm.chat to return a canned response (avoids real LLM calls)."""
    with patch("llm.chat", return_value="Think: test\nDo: attack Goblin") as m:
        yield m


@pytest.fixture
def basic_weapon() -> Item:
    return Item(name="Longsword", slot="weapon", atk=5)


@pytest.fixture
def basic_armor() -> Item:
    return Item(name="Chainmail", slot="armor", pdef=3)


@pytest.fixture
def basic_ring() -> Item:
    return Item(name="Iron Band", slot="ring", mdmg=1, mdef=1)


@pytest.fixture
def mock_agent(basic_weapon, basic_armor, basic_ring) -> AgentState:
    return AgentState(
        name="Kael",
        personality="Brave warrior",
        agent_class="Warrior",
        hp=25,
        max_hp=25,
        mp=0,
        max_mp=0,
        weapon=basic_weapon,
        armor=basic_armor,
        ring=basic_ring,
        room_id="room_1",
        ap=10,
        max_ap=10,
        speed=3,
    )


@pytest.fixture
def mock_mage() -> AgentState:
    return AgentState(
        name="Lyria",
        personality="Strategic mage",
        agent_class="Mage",
        hp=8,
        max_hp=8,
        mp=25,
        max_mp=25,
        weapon=Item(name="Oak Staff", slot="weapon", atk=2),
        armor=Item(name="Mage Robes", slot="armor", pdef=1, mdef=3),
        ring=Item(name="Sapphire Focus", slot="ring", mdmg=5, mdef=2),
        room_id="room_1",
        speed=4,
    )


@pytest.fixture
def mock_ranger() -> AgentState:
    return AgentState(
        name="Finn",
        personality="Practical ranger",
        agent_class="Ranger",
        hp=14,
        max_hp=14,
        mp=10,
        max_mp=10,
        weapon=Item(name="Hunting Bow", slot="weapon", atk=4),
        armor=Item(name="Leather Armor", slot="armor", pdef=2, mdef=1),
        ring=Item(name="Emerald Charm", slot="ring", mdmg=3, mdef=1),
        room_id="room_1",
        speed=5,
    )


@pytest.fixture
def mock_mob() -> Mob:
    return Mob(name="Goblin Scout", hp=4, max_hp=4, atk=2)


@pytest.fixture
def mock_boss() -> Mob:
    return Mob(name="Void Lord", hp=30, max_hp=30, atk=6, mdef=2, is_boss=True)


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
