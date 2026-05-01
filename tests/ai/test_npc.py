"""Tests for npc_ai.py — NPC dialogue with stubbed LLM + summarizer."""
from __future__ import annotations

import pytest

from nachomud.characters.character import create_character
from nachomud.models import NPC
from nachomud.ai.npc import NPCDialogue, build_npc_system, build_npc_user_prompt
from nachomud.rules.stats import Stats


def _player():
    s = Stats(STR=15, DEX=12, CON=14, INT=8, WIS=10, CHA=13)
    return create_character("Aric", "Dwarf", "Warrior", s, player_id="p1")


def _john():
    return NPC(
        npc_id="john", name="Old John", title="Blacksmith",
        personality="A weathered Dwarf with soot-blackened hands. Gruff but proud.",
    )


def test_speak_returns_reply_and_summary():
    npc_calls = []
    sum_calls = []
    npc = NPCDialogue(
        llm=lambda s, u: (npc_calls.append((s, u)) or "Aye, traveler. What'll ye be needing?"),
        summarizer=lambda s, u: (sum_calls.append((s, u)) or "John greets the traveler."),
    )
    p = _player()
    j = _john()
    reply, summary = npc.speak(p, j, "working the forge", "Hello.")
    assert "Aye" in reply
    assert "John greets" in summary
    # Lore was appended to player history
    assert any("John greets" in line for line in p.lore_history)


def test_lore_history_capped(monkeypatch):
    monkeypatch.setattr("nachomud.ai.npc.LORE_HISTORY_SIZE", 3)
    npc = NPCDialogue(
        llm=lambda s, u: "ok.",
        summarizer=lambda s, u: "summary.",
    )
    p = _player()
    j = _john()
    for _ in range(6):
        npc.speak(p, j, "idle", "hello")
    assert len(p.lore_history) == 3


def test_npc_system_includes_personality_and_activity():
    sys_prompt = build_npc_system(_john(), "working the forge")
    assert "Old John" in sys_prompt
    assert "Blacksmith" in sys_prompt
    assert "soot-blackened" in sys_prompt
    assert "working the forge" in sys_prompt


def test_npc_user_prompt_includes_player_identity_and_message():
    p = _player()
    j = _john()
    prompt = build_npc_user_prompt(j, p, "Where can I buy a sword?")
    assert "Aric" in prompt
    assert "Dwarf" in prompt
    assert "Warrior" in prompt
    assert "buy a sword" in prompt


def test_npc_user_prompt_includes_wares_list():
    from nachomud.models import NPC
    p = _player()
    seller = NPC(npc_id="g", name="Greta", title="Fruit Seller",
                 wares=[{"name": "Red Apple", "price": 2}, {"name": "Pear", "price": 3}])
    prompt = build_npc_user_prompt(seller, p, "what do you have?")
    assert "Red Apple" in prompt
    assert "2 gp" in prompt


def test_speak_handles_llm_failure_gracefully():
    def boom(s, u):
        raise RuntimeError("ollama is down")
    npc = NPCDialogue(llm=boom, summarizer=lambda s, u: "n/a")
    p = _player()
    reply, summary = npc.speak(p, _john(), "idle", "hello")
    assert "Old John" in reply  # fallback message
    assert summary == ""  # we don't log on full failure
    assert p.lore_history == []  # nothing appended


def test_speak_handles_summarizer_failure():
    def boom_sum(s, u):
        raise RuntimeError("summary down")
    npc = NPCDialogue(llm=lambda s, u: "Hello there, traveler.", summarizer=boom_sum)
    p = _player()
    reply, summary = npc.speak(p, _john(), "idle", "hello")
    assert "Hello there" in reply
    # Fallback summary uses raw NPC text
    assert "Old John" in summary
    assert any("Old John" in line for line in p.lore_history)
