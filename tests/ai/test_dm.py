"""Tests for dm.py — DM stub conversation."""
from __future__ import annotations

import pytest

from nachomud.characters.character import create_character
from nachomud.ai.dm import DM, DM_PERSONA, _build_user_prompt
from nachomud.models import Room
from nachomud.rules.stats import Stats


def _agent():
    s = Stats(STR=15, DEX=12, CON=14, INT=8, WIS=10, CHA=13)
    a = create_character("Aric", "Dwarf", "Warrior", s, player_id="p1",
                         respawn_room="silverbrook.inn", world_id="default")
    a.room_id = "silverbrook.inn"
    return a


def _room():
    return Room(
        id="silverbrook.inn",
        name="Bronze Hart Inn",
        description="A warm common room.",
        exits={"north": "silverbrook.market_square"},
    )


def test_respond_uses_injected_llm():
    captured = {}
    def stub(system: str, user: str) -> str:
        captured["system"] = system
        captured["user"] = user
        return "The hearth crackles. The innkeeper nods."
    dm = DM(llm=stub)
    a = _agent()
    reply = dm.respond(a, _room(), "What's that smell?")
    assert "hearth" in reply.lower()
    assert captured["system"] == DM_PERSONA
    assert "Aric" in captured["user"]
    assert "Dwarf" in captured["user"]
    assert "What's that smell?" in captured["user"]


def test_respond_appends_to_context():
    dm = DM(llm=lambda s, u: "ok.")
    a = _agent()
    dm.respond(a, _room(), "hello?")
    dm.respond(a, _room(), "how does this place look?")
    exchanges = a.dm_context["recent_exchanges"]
    assert len(exchanges) == 2
    assert exchanges[0]["player"] == "hello?"
    assert exchanges[1]["dm"] == "ok."


def test_respond_trims_at_cap():
    from nachomud.settings import DM_RECENT_EXCHANGES_CAP
    dm = DM(llm=lambda s, u: "ok.")
    a = _agent()
    for i in range(DM_RECENT_EXCHANGES_CAP + 5):
        dm.respond(a, _room(), f"q{i}")
    assert len(a.dm_context["recent_exchanges"]) == DM_RECENT_EXCHANGES_CAP


def test_respond_handles_llm_exceptions():
    def boom(s, u):
        raise RuntimeError("ollama is down")
    dm = DM(llm=boom)
    a = _agent()
    reply = dm.respond(a, _room(), "anything?")
    assert "falters" in reply.lower() or "DM" in reply or "RuntimeError" in reply
    # Still recorded in context (so the player save round-trips)
    assert len(a.dm_context["recent_exchanges"]) == 1


def test_prompt_includes_recent_exchanges():
    a = _agent()
    a.dm_context["recent_exchanges"].append({"player": "earlier q", "dm": "earlier reply"})
    prompt = _build_user_prompt(a, _room(), "follow-up")
    assert "earlier q" in prompt
    assert "earlier reply" in prompt
    assert "follow-up" in prompt


def test_prompt_includes_summary_when_present():
    a = _agent()
    a.dm_context["summary"] = "Aric arrived in town this morning."
    prompt = _build_user_prompt(a, _room(), "what's next?")
    assert "Aric arrived" in prompt
