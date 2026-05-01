"""Tests for the combat-mode UX fixes:
- 'punch <mob>' (and other attack synonyms) trigger combat
- 'dm <message>' works mid-combat without consuming the player's turn
- 'stats' shows XP and progress to next level
- DM short-circuits self-status queries (XP, gold, HP) deterministically
"""
from __future__ import annotations

import pytest

import nachomud.rules.dice as dice
import nachomud.characters.save as player_mod
import nachomud.world.starter as starter
import nachomud.world.store as world_store
from nachomud.characters.character import create_character
from nachomud.combat.encounter import Encounter
from nachomud.ai.dm import DM
from nachomud.engine.game import Game
from nachomud.models import Mob, Room
from nachomud.ai.npc import NPCDialogue
from nachomud.rules.stats import Stats


@pytest.fixture
def world(tmp_path, monkeypatch):
    monkeypatch.setattr(world_store, "DATA_ROOT", str(tmp_path / "world"))
    monkeypatch.setattr(player_mod, "DATA_ROOT", str(tmp_path / "players"))
    starter.seed_world("default")
    return tmp_path


@pytest.fixture
def aric(world):
    s = Stats(STR=15, DEX=12, CON=14, INT=8, WIS=10, CHA=13)
    a = create_character("Aric", "Dwarf", "Warrior", s,
                         player_id="p1", respawn_room="silverbrook.inn", world_id="default")
    a.room_id = "silverbrook.inn"
    player_mod.save_player(a)
    return a


def _spawn_goblin(world_id, room_id, mob_id="g1"):
    m = Mob(name="Goblin", hp=10, max_hp=10, atk=2, ac=11, level=1,
            stats={"STR": 8, "DEX": 14, "CON": 10, "INT": 8, "WIS": 8, "CHA": 6},
            damage_die="1d4", damage_bonus=2,
            faction="goblin_clan", aggression=7,
            home_room=room_id, current_room=room_id,
            zone_tag="silverbrook_town", mob_id=mob_id, kind="goblin",
            abilities=["attack"], xp_value=25)
    world_store.add_mob(world_id, m)
    return m


def _text(msgs):
    return "".join(m[1] for m in msgs if isinstance(m, tuple) and m[0] == "output")


def _stub_dm():
    return DM(llm=lambda s, u: "ok.")


def _stub_npc():
    return NPCDialogue(llm=lambda s, u: "Aye.", summarizer=lambda s, u: "s.")


# ── attack fast-path + DM engage_combat ──

def test_attack_command_engages_combat(aric):
    _spawn_goblin(aric.world_id, aric.room_id)
    g = Game(player=aric, dm=_stub_dm(), npc_dialogue=_stub_npc())
    g.start()
    msgs = g.handle("attack goblin")
    text = _text(msgs)
    assert "Combat begins" in text
    assert g._encounter is not None


def test_natural_attack_verb_routes_through_dm(aric):
    """'punch goblin' falls through to DM adjudication. The DM is free to
    narrate-only OR emit an engage_combat action to start combat."""
    import json
    _spawn_goblin(aric.world_id, aric.room_id)
    # Stub DM that recognizes the attack and emits engage_combat
    dm = DM(llm=lambda s, u: json.dumps({
        "narrate": "You charge the goblin, fists raised.",
        "actions": [{"type": "engage_combat", "target": "Goblin"}],
    }))
    g = Game(player=aric, dm=dm, npc_dialogue=_stub_npc())
    g.start()
    msgs = g.handle("punch goblin")
    text = _text(msgs)
    assert "fists raised" in text
    assert "Combat begins" in text
    assert g._encounter is not None


def test_dm_engage_with_unknown_target_does_not_start_combat(aric):
    import json
    # No mob spawned. DM (mistakenly) emits engage_combat anyway.
    dm = DM(llm=lambda s, u: json.dumps({
        "narrate": "You shadow-box at the air.",
        "actions": [{"type": "engage_combat", "target": "Phantom"}],
    }))
    g = Game(player=aric, dm=dm, npc_dialogue=_stub_npc())
    g.start()
    msgs = g.handle("punch the phantom")
    assert g._encounter is None  # validator rejected
    assert "shadow-box" in _text(msgs)


def test_punch_without_target_still_falls_through(aric):
    _spawn_goblin(aric.world_id, aric.room_id)
    g = Game(player=aric, dm=_stub_dm(), npc_dialogue=_stub_npc())
    g.start()
    # "punch" alone has no arg → DM adjudication, no combat
    msgs = g.handle("punch")
    assert "DM:" in _text(msgs)
    assert g._encounter is None


# ── DM works mid-combat ──

def test_dm_command_works_mid_combat(aric):
    _spawn_goblin(aric.world_id, aric.room_id)
    g = Game(player=aric, dm=_stub_dm(), npc_dialogue=_stub_npc())
    g.start()
    g.handle("attack goblin")
    assert g._encounter is not None
    msgs = g.handle("dm what should I do?")
    text = _text(msgs)
    assert "DM:" in text
    # Combat still active — DM chat doesn't end it
    assert g._encounter is not None
    assert g._encounter.is_active()


def test_ask_alias_works_mid_combat(aric):
    _spawn_goblin(aric.world_id, aric.room_id)
    g = Game(player=aric, dm=_stub_dm(), npc_dialogue=_stub_npc())
    g.start()
    g.handle("attack goblin")
    msgs = g.handle("ask should I run?")
    assert "DM:" in _text(msgs)


def test_dm_no_arg_in_combat_prompts(aric):
    _spawn_goblin(aric.world_id, aric.room_id)
    g = Game(player=aric, dm=_stub_dm(), npc_dialogue=_stub_npc())
    g.start()
    g.handle("attack goblin")
    msgs = g.handle("dm")
    assert "about what" in _text(msgs).lower()


def test_help_works_in_combat(aric):
    _spawn_goblin(aric.world_id, aric.room_id)
    g = Game(player=aric, dm=_stub_dm(), npc_dialogue=_stub_npc())
    g.start()
    g.handle("attack goblin")
    msgs = g.handle("help")
    text = _text(msgs)
    assert "Combat commands" in text
    assert "dm <message>" in text


# ── XP in stats ──

def test_stats_shows_xp_and_progress_to_next(aric):
    aric.xp = 150
    g = Game(player=aric, dm=_stub_dm(), npc_dialogue=_stub_npc())
    g.start()
    msgs = g.handle("stats")
    text = _text(msgs)
    assert "XP" in text or "xp" in text.lower()
    assert "150" in text  # current XP
    assert "L2" in text  # next level


# ── DM XP/gold/HP self-status short-circuits ──

def test_dm_xp_query_returns_real_value(aric):
    aric.xp = 200
    dm = DM(llm=lambda s, u: "should-not-be-called")
    reply = dm.respond(aric, Room(id="r", name="r"), "what's my xp?")
    assert "200" in reply
    assert "L2" in reply or "Level 2" in reply


def test_dm_gold_query_returns_real_value(aric):
    aric.gold = 17
    dm = DM(llm=lambda s, u: "should-not-be-called")
    reply = dm.respond(aric, Room(id="r", name="r"), "how much gold do I have?")
    assert "17" in reply


def test_dm_hp_query_returns_real_value(aric):
    aric.hp = 4
    dm = DM(llm=lambda s, u: "should-not-be-called")
    reply = dm.respond(aric, Room(id="r", name="r"), "how much hp do I have?")
    assert "4" in reply
    assert str(aric.max_hp) in reply


def test_dm_level_query_returns_real_value(aric):
    aric.level = 3
    aric.xp = 1000
    dm = DM(llm=lambda s, u: "should-not-be-called")
    reply = dm.respond(aric, Room(id="r", name="r"), "how do i level up?")
    assert "Level 3" in reply or "L3" in reply
