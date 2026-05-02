"""LLMUnavailable propagation through DM / NPC / world_gen / move
command. The GPU box can be stopped independently of the app box —
when it's off, every LLM-using path must degrade gracefully instead
of hanging or crashing."""
from __future__ import annotations

import pytest

import nachomud.world.store as world_store
from nachomud.ai.dm import DM
from nachomud.ai.llm import LLMUnavailable
from nachomud.ai.npc import NPCDialogue
from nachomud.ai.world_gen import WorldGen
from nachomud.models import NPC, Room


def _raises_unavailable(*_a, **_kw):
    raise LLMUnavailable("ollama unreachable: test")


def _player_with(name="Aric", room_id="silverbrook.inn"):
    from nachomud.characters.character import create_character
    from nachomud.rules.stats import Stats
    p = create_character(name, "Dwarf", "Warrior",
                         Stats(STR=15, DEX=12, CON=14, INT=8, WIS=10, CHA=13))
    p.room_id = room_id
    return p


def test_dm_respond_returns_clean_message_when_llm_off():
    dm = DM(llm=_raises_unavailable)
    p = _player_with()
    room = Room(id="silverbrook.inn", name="Inn", description="cozy")
    reply = dm.respond(p, room, "what news?")
    assert "silent for the moment" in reply
    # Must not leak the exception class name into the player-facing string.
    assert "LLMUnavailable" not in reply
    assert "Exception" not in reply


def test_dm_adjudicate_returns_clean_payload_when_llm_off():
    dm = DM(llm=_raises_unavailable)
    p = _player_with()
    room = Room(id="silverbrook.inn", name="Inn", description="cozy")
    result = dm.adjudicate(p, room, "I push the bookcase")
    assert "world feels paused" in result["narrate"]
    assert "LLMUnavailable" not in result["narrate"]


def test_npc_speak_returns_clean_fallback_when_llm_off():
    npc_dialogue = NPCDialogue(llm=_raises_unavailable, summarizer=lambda s, u: "")
    p = _player_with()
    npc = NPC(npc_id="marta", name="Old Marta", title="Innkeeper",
              personality="kind", lore=["ale is fresh"])
    reply, _summary = npc_dialogue.speak(p, npc, "tending bar", "hello")
    # Existing NPCDialogue fallback returns a generic "doesn't hear you"
    # message — fine for the LLM-off case too. Verify it doesn't crash
    # and doesn't leak the exception class name.
    assert "LLMUnavailable" not in reply
    assert "doesn't seem to hear" in reply or "doesn't hear" in reply


def test_world_gen_room_propagates_unavailable_instead_of_stubbing(tmp_path,
                                                                    monkeypatch):
    """Critical: when the LLM is OFF (not just slow), we must NOT
    create a permanent stub room. The map would be polluted with
    'Uncharted Place' rooms forever. Bubble up so the move command
    can refuse the action."""
    monkeypatch.setattr(world_store, "DATA_ROOT", str(tmp_path))
    wg = WorldGen(llm=_raises_unavailable)
    src = Room(id="silverbrook.inn", name="Inn", description="cozy",
               exits={"n": "wild.foo"}, zone_tag="silverbrook")
    with pytest.raises(LLMUnavailable):
        wg.generate_room(src, "n", "default", requested_id="wild.foo")
