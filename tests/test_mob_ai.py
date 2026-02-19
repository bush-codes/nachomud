"""Tests for mob_ai.py — prompt building, action parsing, taunt/sleep enforcement, resolution."""
from __future__ import annotations

from unittest.mock import patch

from effects import apply_effect
from mob_ai import (
    _find_taunter,
    _parse_mob_action,
    _parse_mob_comm,
    _parse_mob_command,
    build_mob_action_prompt,
    build_mob_comm_prompt,
    get_mob_action,
    get_mob_comm,
    resolve_mob_ability,
)
from models import AgentState, Item, Mob, Room, StatusEffect


def _make_agent(name="Kael", agent_class="Warrior", hp=25, room_id="room_1") -> AgentState:
    return AgentState(
        name=name,
        personality="Test",
        agent_class=agent_class,
        hp=hp,
        max_hp=hp,
        mp=0,
        max_mp=0,
        weapon=Item(name="Sword", slot="weapon", atk=5),
        armor=Item(name="Armor", slot="armor", pdef=3),
        ring=Item(name="Ring", slot="ring"),
        room_id=room_id,
        speed=3,
    )


def _make_mob(name="Goblin", hp=10, atk=4, room_id="room_1", abilities=None, is_boss=False) -> Mob:
    return Mob(
        name=name,
        hp=hp,
        max_hp=hp,
        atk=atk,
        room_id=room_id,
        abilities=abilities or ["attack"],
        is_boss=is_boss,
        speed=3,
    )


# ── Prompt building ──


def test_build_mob_action_prompt():
    mob = _make_mob(abilities=["attack", "curse"])
    room = Room(id="room_1", name="Dark Hall")
    agent = _make_agent()

    prompt = build_mob_action_prompt(mob, room, [agent])
    assert "Goblin" in prompt
    assert "Kael" in prompt
    assert "attack" in prompt
    assert "curse" in prompt
    assert "Dark Hall" in prompt


def test_build_mob_comm_prompt():
    mob = _make_mob(is_boss=True)
    room = Room(id="room_1", name="Throne Room")
    agent = _make_agent()

    prompt = build_mob_comm_prompt(mob, room, [agent])
    assert "Goblin" in prompt
    assert "Kael" in prompt


# ── Parsing ──


def test_parse_mob_action_with_do():
    assert _parse_mob_action("Think: I should attack\nDo: attack Kael") == "attack Kael"


def test_parse_mob_action_fallback():
    assert _parse_mob_action("attack Kael") == "attack Kael"


def test_parse_mob_action_strips_slash():
    assert _parse_mob_action("Do: /attack Kael") == "attack Kael"


def test_parse_mob_comm_say_prefix():
    assert _parse_mob_comm("Say: You shall perish!") == "You shall perish!"


def test_parse_mob_comm_none():
    assert _parse_mob_comm("none") is None
    assert _parse_mob_comm("None.") is None
    assert _parse_mob_comm("silent") is None


def test_parse_mob_comm_plain():
    assert _parse_mob_comm("Die, adventurer!") == "Die, adventurer!"


def test_parse_mob_command_basic():
    assert _parse_mob_command("attack Kael") == ("attack", "Kael")
    assert _parse_mob_command("curse Lyria") == ("curse", "Lyria")
    assert _parse_mob_command("") == ("attack", "")


# ── Taunt enforcement ──


def test_find_taunter():
    mob = _make_mob()
    agent = _make_agent()
    apply_effect(mob, StatusEffect("taunted", "Kael", 1))
    taunter = _find_taunter(mob, [agent])
    assert taunter is agent


def test_find_taunter_not_in_room():
    mob = _make_mob()
    agent = _make_agent(room_id="room_2")
    apply_effect(mob, StatusEffect("taunted", "Kael", 1))
    taunter = _find_taunter(mob, [agent])
    assert taunter is None


def test_find_taunter_none():
    mob = _make_mob()
    agent = _make_agent()
    taunter = _find_taunter(mob, [agent])
    assert taunter is None


# ── get_mob_action ──


def test_get_mob_action_sleep_skips():
    mob = _make_mob()
    apply_effect(mob, StatusEffect("asleep", "Ranger", 2))
    room = Room(id="room_1", name="Test")
    agent = _make_agent()

    cmd, arg = get_mob_action(mob, room, [agent], {"room_1": room}, tick=1)
    assert cmd == ""  # skipped


def test_get_mob_action_no_agents():
    mob = _make_mob()
    room = Room(id="room_1", name="Test")

    cmd, arg = get_mob_action(mob, room, [], {"room_1": room}, tick=1)
    assert cmd == ""  # no targets


@patch("mob_ai.chat", return_value="Think: Kill the warrior\nDo: attack Kael")
def test_get_mob_action_basic(mock_chat):
    mob = _make_mob()
    room = Room(id="room_1", name="Test")
    agent = _make_agent()

    cmd, arg = get_mob_action(mob, room, [agent], {"room_1": room}, tick=1)
    assert cmd == "attack"
    assert arg == "Kael"


@patch("mob_ai.chat", return_value="Think: Kill them\nDo: attack Nobody")
def test_get_mob_action_invalid_target_fallback(mock_chat):
    mob = _make_mob()
    room = Room(id="room_1", name="Test")
    agent = _make_agent()

    cmd, arg = get_mob_action(mob, room, [agent], {"room_1": room}, tick=1)
    assert cmd == "attack"
    assert arg == "Kael"  # fallback to available agent


@patch("mob_ai.chat", return_value="Think: Use fireball\nDo: fireball")
def test_get_mob_action_invalid_ability_fallback(mock_chat):
    mob = _make_mob(abilities=["attack"])  # doesn't have fireball
    room = Room(id="room_1", name="Test")
    agent = _make_agent()

    cmd, arg = get_mob_action(mob, room, [agent], {"room_1": room}, tick=1)
    assert cmd == "attack"  # fallback


@patch("mob_ai.chat", return_value="Think: Kill them\nDo: attack Lyria")
def test_get_mob_action_taunt_overrides_target(mock_chat):
    mob = _make_mob()
    apply_effect(mob, StatusEffect("taunted", "Kael", 1))
    room = Room(id="room_1", name="Test")
    agent = _make_agent()
    mage = _make_agent("Lyria", "Mage", hp=8)

    cmd, arg = get_mob_action(mob, room, [agent, mage], {"room_1": room}, tick=1)
    assert cmd == "attack"
    assert arg == "Kael"  # taunt overrides to Kael


# ── get_mob_comm ──


def test_get_mob_comm_sleep_silent():
    mob = _make_mob(is_boss=True)
    apply_effect(mob, StatusEffect("asleep", "Ranger", 2))
    room = Room(id="room_1", name="Test")
    agent = _make_agent()

    result = get_mob_comm(mob, room, [agent])
    assert result is None


@patch("mob_ai.chat", return_value="You will die!")
def test_get_mob_comm_boss_always_talks(mock_chat):
    mob = _make_mob(is_boss=True)
    room = Room(id="room_1", name="Test")
    agent = _make_agent()

    result = get_mob_comm(mob, room, [agent])
    assert result == "You will die!"


# ── resolve_mob_ability ──


def test_resolve_mob_attack():
    mob = _make_mob(atk=4)
    agent = _make_agent(hp=25)
    room = Room(id="room_1", name="Test")

    events = resolve_mob_ability(mob, "attack", "Kael", room, tick=1, agents=[agent])
    assert len(events) == 1
    assert "attacks" in events[0].result
    # mob.atk=4, agent pdef=3+0=3, damage = max(1, 4-3) = 1
    assert agent.hp == 24


def test_resolve_mob_attack_no_target():
    mob = _make_mob()
    room = Room(id="room_1", name="Test")

    events = resolve_mob_ability(mob, "attack", "Nobody", room, tick=1, agents=[])
    assert "air" in events[0].result


def test_resolve_mob_attack_kills_agent():
    mob = _make_mob(atk=10)
    agent = _make_agent(hp=3)
    room = Room(id="room_1", name="Test")

    events = resolve_mob_ability(mob, "attack", "Kael", room, tick=1, agents=[agent])
    assert agent.hp == 0
    assert not agent.alive
    assert "fallen" in events[0].result.lower()


def test_resolve_mob_dot():
    mob = _make_mob()
    agent = _make_agent()
    room = Room(id="room_1", name="Test")

    events = resolve_mob_ability(mob, "curse", "Kael", room, tick=1, agents=[agent])
    assert "curse" in events[0].result.lower()
    assert any(se.name == "cursed" for se in agent.status_effects)


def test_resolve_mob_sleep():
    mob = _make_mob()
    agent = _make_agent()
    room = Room(id="room_1", name="Test")

    events = resolve_mob_ability(mob, "sleep", "Kael", room, tick=1, agents=[agent])
    assert "sleep" in events[0].result.lower()
    assert any(se.name == "asleep" for se in agent.status_effects)


def test_resolve_mob_heal():
    mob = _make_mob(hp=10)
    mob.hp = 5  # damage the mob first
    room = Room(id="room_1", name="Test")

    events = resolve_mob_ability(mob, "heal", "", room, tick=1, agents=[])
    assert "heals" in events[0].result.lower()
    assert mob.hp > 5


def test_resolve_mob_aoe():
    mob = _make_mob(atk=4)
    agent1 = _make_agent("Kael", hp=25)
    agent2 = _make_agent("Lyria", "Mage", hp=8)
    room = Room(id="room_1", name="Test")

    events = resolve_mob_ability(mob, "cleave", "", room, tick=1, agents=[agent1, agent2])
    assert len(events) == 1
    assert "Kael" in events[0].result
    assert "Lyria" in events[0].result


def test_resolve_mob_ability_asleep():
    mob = _make_mob()
    apply_effect(mob, StatusEffect("asleep", "Ranger", 2))
    agent = _make_agent()
    room = Room(id="room_1", name="Test")

    events = resolve_mob_ability(mob, "attack", "Kael", room, tick=1, agents=[agent])
    assert "asleep" in events[0].result.lower()
