"""Tests for dm.generate_room — DM-driven procedural room generation."""
from __future__ import annotations

import json

import pytest

import nachomud.characters.save as player_mod
import nachomud.world.starter as starter
import nachomud.world.store as world_store
from nachomud.characters.character import create_character
from nachomud.ai.dm import DM
from nachomud.engine.game import Game
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
    a.room_id = "silverbrook.watchtower"  # at the frontier
    player_mod.save_player(a)
    return a


def _llm_returning(payload: dict):
    """Build a fake LLM that returns the given payload as JSON."""
    return lambda system, user: json.dumps(payload)


SAMPLE_PAYLOAD = {
    "name": "Pale Grass Plains",
    "description": "Endless rolling grass, the wind moves through it like water.",
    "zone_tag": "wild_plains",
    "exits": ["north", "east"],
    "npcs": [],
    "mobs": [
        {
            "name": "Lean Wolf", "hp": 8, "ac": 12,
            "stats": {"STR": 12, "DEX": 14, "CON": 10, "INT": 4, "WIS": 12, "CHA": 6},
            "damage_die": "1d6", "damage_bonus": 2,
            "faction": "wild_beast", "aggression": 6, "xp_value": 25,
        },
    ],
    "items": [
        {"name": "Bone Whistle", "slot": "consumable"},
    ],
}


# ── Direct generate_room ──

def test_generate_room_creates_persistent_room(world):
    dm = DM(llm=_llm_returning(SAMPLE_PAYLOAD))
    source = world_store.load_room("default", "silverbrook.watchtower")
    new_room = dm.generate_room(source, "north", "default",
                                requested_id="wild.frontier_north")
    assert new_room.id == "wild.frontier_north"
    assert new_room.name == "Pale Grass Plains"
    assert new_room.zone_tag == "wild_plains"
    # Persisted
    assert world_store.room_exists("default", "wild.frontier_north")
    # Back-edge to source
    reloaded = world_store.load_room("default", "wild.frontier_north")
    assert reloaded.exits.get("south") == "silverbrook.watchtower"


def test_generate_room_adds_forward_placeholder_exits(world):
    dm = DM(llm=_llm_returning(SAMPLE_PAYLOAD))
    source = world_store.load_room("default", "silverbrook.watchtower")
    new_room = dm.generate_room(source, "north", "default",
                                requested_id="wild.frontier_north")
    # Forward exits are present and point to non-existent rooms (placeholders)
    assert "north" in new_room.exits or "east" in new_room.exits
    for d in ("north", "east"):
        if d in new_room.exits:
            dest = new_room.exits[d]
            assert dest != "silverbrook.watchtower"
            assert not world_store.room_exists("default", dest)  # placeholder


def test_generate_room_spawns_mobs(world):
    dm = DM(llm=_llm_returning(SAMPLE_PAYLOAD))
    source = world_store.load_room("default", "silverbrook.watchtower")
    dm.generate_room(source, "north", "default", requested_id="wild.frontier_north")

    mobs = world_store.mobs_in_room("default", "wild.frontier_north")
    assert len(mobs) == 1
    m = mobs[0]
    assert m.name == "Lean Wolf"
    assert m.faction == "wild_beast"
    assert m.zone_tag == "wild_plains"
    assert m.home_room == "wild.frontier_north"


def test_generate_room_spawns_items(world):
    dm = DM(llm=_llm_returning(SAMPLE_PAYLOAD))
    source = world_store.load_room("default", "silverbrook.watchtower")
    dm.generate_room(source, "north", "default", requested_id="wild.frontier_north")
    items = world_store.items_in_room("default", "wild.frontier_north")
    assert len(items) == 1
    assert items[0]["name"] == "Bone Whistle"


def test_generate_room_writes_graph_edge(world):
    dm = DM(llm=_llm_returning(SAMPLE_PAYLOAD))
    source = world_store.load_room("default", "silverbrook.watchtower")
    dm.generate_room(source, "north", "default", requested_id="wild.frontier_north")
    g = world_store.load_graph("default")
    assert g["silverbrook.watchtower"]["north"] == "wild.frontier_north"
    assert g["wild.frontier_north"]["south"] == "silverbrook.watchtower"


def test_generate_room_handles_messy_llm_output(world):
    """LLM may wrap JSON in chatter or markdown fences. Parser should cope."""
    raw = "Here's the room you asked for:\n```json\n" + json.dumps(SAMPLE_PAYLOAD) + "\n```\n"
    dm = DM(llm=lambda s, u: raw)
    source = world_store.load_room("default", "silverbrook.watchtower")
    new_room = dm.generate_room(source, "north", "default",
                                requested_id="wild.frontier_north")
    assert new_room.name == "Pale Grass Plains"


def test_generate_room_falls_back_on_total_garbage(world):
    """Bad LLM output → stub room rather than crashing the player."""
    dm = DM(llm=lambda s, u: "lol nope.")
    source = world_store.load_room("default", "silverbrook.watchtower")
    new_room = dm.generate_room(source, "north", "default",
                                requested_id="wild.frontier_north", max_retries=0)
    assert "fallback" in new_room.description.lower() or new_room.name == "Misty Crossing"
    # Still persisted with a back-edge so we don't break movement
    assert world_store.room_exists("default", "wild.frontier_north")
    reloaded = world_store.load_room("default", "wild.frontier_north")
    assert reloaded.exits.get("south") == "silverbrook.watchtower"


# ── Through Game (player movement triggers generation) ──

def test_player_movement_triggers_generation(world, aric):
    g = Game(player=aric, dm=DM(llm=_llm_returning(SAMPLE_PAYLOAD)),
             npc_dialogue=NPCDialogue(llm=lambda s, u: "ok", summarizer=lambda s, u: "s"))
    g.start()
    # Player at watchtower; "north" leads to the frontier placeholder
    msgs = g.handle("north")
    text = "".join(m[1] for m in msgs if isinstance(m, tuple) and m[0] == "output")
    assert "Pale Grass Plains" in text
    assert aric.room_id == "wild.frontier_north"
    assert world_store.room_exists("default", "wild.frontier_north")


def test_subsequent_visit_uses_cached_room(world, aric):
    """The same room JSON is loaded on revisit; LLM is NOT called twice."""
    call_count = [0]

    def counting_llm(s, u):
        call_count[0] += 1
        return json.dumps(SAMPLE_PAYLOAD)

    g = Game(player=aric, dm=DM(llm=counting_llm),
             npc_dialogue=NPCDialogue(llm=lambda s, u: "ok", summarizer=lambda s, u: "s"))
    g.start()
    g.handle("north")
    g.handle("south")  # back to watchtower
    calls_after_first = call_count[0]
    g.handle("north")  # re-enter generated room
    assert call_count[0] == calls_after_first  # no second LLM call


# ── Race guard: idempotent on requested_id ──

def test_generate_room_skips_llm_when_room_already_exists(world):
    """If the requested_id already maps to a persisted room (another
    actor raced ahead on their own GPU and created it first), we must
    return that room and NOT call the LLM. Belt-and-suspenders against
    a concurrent-write race that the WorldLoop lock currently prevents,
    but which we want world_gen itself to be safe against."""
    from nachomud.models import Room
    pre_existing = Room(id="wild.frontier_north", name="Pre-Existing Plains",
                        description="Already on the map.", zone_tag="wild_plains",
                        exits={"south": "silverbrook.watchtower"})
    world_store.save_room("default", pre_existing)

    call_count = [0]
    def counting_llm(s, u):
        call_count[0] += 1
        return json.dumps(SAMPLE_PAYLOAD)

    dm = DM(llm=counting_llm)
    source = world_store.load_room("default", "silverbrook.watchtower")
    result = dm.generate_room(source, "north", "default",
                              requested_id="wild.frontier_north")

    assert call_count[0] == 0  # LLM never called
    assert result.name == "Pre-Existing Plains"  # got the existing room, not a fresh one