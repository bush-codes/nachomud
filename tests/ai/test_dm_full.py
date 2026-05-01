"""Tests for Phase 10 DM full powers: adjudication, hints, interjections."""
from __future__ import annotations

import json

import pytest

import nachomud.rules.dice as dice
from nachomud.characters.character import create_character
from nachomud.ai.dm import DM, _extract_hint
from nachomud.models import Room
from nachomud.rules.stats import Stats


def _player():
    s = Stats(STR=15, DEX=12, CON=14, INT=8, WIS=10, CHA=13)
    return create_character("Aric", "Dwarf", "Warrior", s, player_id="p1",
                            respawn_room="silverbrook.inn", world_id="default")


def _room():
    return Room(id="r1", name="Library", description="Dusty bookshelves line the walls.",
                exits={"south": "r0"})


# ── HINT extraction ──

def test_extract_hint_inline():
    text, hint = _extract_hint("There's an inn nearby.\nHINT: An inn lies 2 rooms north.\n")
    assert "inn nearby" in text
    assert hint == "An inn lies 2 rooms north."


def test_extract_hint_none_when_absent():
    text, hint = _extract_hint("Just narration here.")
    assert text == "Just narration here."
    assert hint is None


# ── Adjudication ──

def test_adjudicate_pure_narration():
    dm = DM(llm=lambda s, u: json.dumps({
        "narrate": "You admire the view. The setting sun gilds the rooftops.",
        "skill_check": None, "hint": None,
    }))
    p = _player()
    out = dm.adjudicate(p, _room(), "I admire the view")
    assert "admire the view" in out["narrate"]
    assert out["skill_check_result"] is None
    assert out["hint"] is None


def test_adjudicate_with_skill_check_success():
    dice.seed(1)
    dm = DM(llm=lambda s, u: json.dumps({
        "narrate": "You set your shoulder to the heavy bookcase.",
        "skill_check": {"stat": "STR", "dc": 10,
                        "on_success": "It scrapes aside, revealing a hidden stair.",
                        "on_fail": "It refuses to budge."},
        "hint": None,
    }))
    p = _player()  # Dwarf Warrior STR 16 = +3
    out = dm.adjudicate(p, _room(), "I push the bookcase")
    sc = out["skill_check_result"]
    assert sc is not None
    assert sc["stat"] == "STR"
    assert sc["dc"] == 10
    assert sc["modifier"] == 3
    # Most rolls vs DC 10 with +3 will succeed
    if sc["success"]:
        assert "hidden stair" in sc["narration"]
    else:
        assert "budge" in sc["narration"]


def test_adjudicate_records_in_dm_context():
    dm = DM(llm=lambda s, u: json.dumps({
        "narrate": "You try.", "skill_check": None, "hint": None,
    }))
    p = _player()
    dm.adjudicate(p, _room(), "I try something")
    assert p.dm_context["recent_exchanges"]
    assert "try something" in p.dm_context["recent_exchanges"][-1]["player"]


def test_adjudicate_with_hint_persists():
    dm = DM(llm=lambda s, u: json.dumps({
        "narrate": "You notice scratch marks on the wall.",
        "skill_check": None,
        "hint": "Hidden passage leads down from the library.",
    }))
    p = _player()
    out = dm.adjudicate(p, _room(), "I look around carefully")
    assert "Hidden passage" in out["hint"]
    assert p.dm_context["pending_hints"]
    assert "Hidden passage" in p.dm_context["pending_hints"][-1]["hint"]


def test_adjudicate_falls_back_on_garbage():
    dm = DM(llm=lambda s, u: "lol that's not json")
    p = _player()
    out = dm.adjudicate(p, _room(), "I do something weird")
    # Falls back to a narration; no crash
    assert "narrate" in out
    assert isinstance(out["narrate"], str)


# ── Inline HINT in chat replies ──

def test_respond_extracts_hint_from_chat():
    dm = DM(llm=lambda s, u: ("There's a healing shrine north of here, near the old oak.\n"
                              "HINT: A healing shrine lies one room north."))
    p = _player()
    reply = dm.respond(p, _room(), "I'm hurt, is there anywhere to heal?")
    # Hint stripped from displayed reply
    assert "HINT" not in reply
    assert "healing shrine" in reply
    # Hint persisted
    assert p.dm_context["pending_hints"]
    assert "healing shrine" in p.dm_context["pending_hints"][-1]["hint"].lower()


# ── Interjections ──

def test_interject_records_exchange():
    dm = DM(llm=lambda s, u: "Aric, your form sharpens with the experience.")
    p = _player()
    reply = dm.interject(p, _room(), "level_up", "Reached L2.")
    assert "Aric" in reply
    assert any("interjection: level_up" in ex["player"]
               for ex in p.dm_context["recent_exchanges"])


def test_interject_handles_llm_failure():
    def boom(s, u): raise RuntimeError("down")
    dm = DM(llm=boom)
    p = _player()
    reply = dm.interject(p, _room(), "level_up")
    assert "level_up" in reply.lower() or "hush" in reply.lower()


# ── Through Game ──

def test_game_unknown_command_routes_to_adjudicate():
    """Free-form input should go through adjudicate (with possible skill check),
    not just plain chat."""
    import nachomud.characters.save as player_mod
    import nachomud.world.starter as starter
    import nachomud.world.store as world_store
    from nachomud.engine.game import Game
    from nachomud.ai.npc import NPCDialogue

    import tempfile, os
    tmp = tempfile.mkdtemp()
    try:
        old_world = world_store.DATA_ROOT
        old_player = player_mod.DATA_ROOT
        world_store.DATA_ROOT = os.path.join(tmp, "world")
        player_mod.DATA_ROOT = os.path.join(tmp, "players")
        try:
            starter.seed_world("default")
            p = _player()
            p.room_id = "silverbrook.inn"
            player_mod.save_player(p)

            adj_calls = []
            def fake(s, u):
                adj_calls.append(u)
                return json.dumps({
                    "narrate": "You attempt the absurd.",
                    "skill_check": None, "hint": None,
                })
            g = Game(player=p, dm=DM(llm=fake),
                     npc_dialogue=NPCDialogue(llm=lambda s, u: "ok",
                                              summarizer=lambda s, u: "s"))
            g.start()
            msgs = g.handle("I attempt to commune with the hearth")
            text = "".join(m[1] for m in msgs if isinstance(m, tuple) and m[0] == "output")
            assert "DM:" in text
            assert "absurd" in text
            assert any("commune" in c for c in adj_calls)
        finally:
            world_store.DATA_ROOT = old_world
            player_mod.DATA_ROOT = old_player
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)
