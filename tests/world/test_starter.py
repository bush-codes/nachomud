"""Tests for starter.py — seeding the hand-authored Silverbrook starter town."""
from __future__ import annotations

import pytest

import nachomud.world.starter as starter
import nachomud.world.store as world_store
@pytest.fixture
def fresh_world(tmp_path, monkeypatch):
    monkeypatch.setattr(world_store, "DATA_ROOT", str(tmp_path / "world"))
    return tmp_path


def test_seed_creates_six_rooms(fresh_world):
    written = starter.seed_world("default")
    assert written == 6
    assert sorted(world_store.list_rooms("default")) == sorted([
        "silverbrook.inn",
        "silverbrook.market_square",
        "silverbrook.smithy",
        "silverbrook.tavern",
        "silverbrook.north_gate",
        "silverbrook.watchtower",
    ])


def test_seed_no_refresh_is_idempotent(fresh_world):
    starter.seed_world("default")
    written2 = starter.seed_world("default", refresh=False)
    assert written2 == 0  # already exist, none re-written


def test_seed_refresh_overwrites_npcs_keeps_flags(fresh_world):
    """Default seed refresh: NPC list updates from JSON, room.flags survive."""
    # First seed
    starter.seed_world("default")
    # Player sets a flag (e.g. opened a secret passage)
    world_store.update_room_flags("default", "silverbrook.market_square",
                                  {"player_marked": True})
    # Re-seed (developer added new NPCs / wares to JSON)
    written = starter.seed_world("default")
    assert written == 6  # all rooms refreshed
    r = world_store.load_room("default", "silverbrook.market_square")
    assert r.flags.get("player_marked") is True  # mutable state preserved
    # Greta should still be present and now have wares (after refresh)
    assert any(n.name == "Greta" and n.wares for n in r.npcs)


def test_inn_has_inn_flag(fresh_world):
    starter.seed_world("default")
    inn = world_store.load_room("default", "silverbrook.inn")
    assert inn.flags.get("is_inn") is True


def test_inn_npc_present_at_morning(fresh_world):
    starter.seed_world("default")
    inn = world_store.load_room("default", "silverbrook.inn")
    assert any(n.name == "Old Marta" for n in inn.npcs)


def test_market_square_has_npcs(fresh_world):
    starter.seed_world("default")
    sq = world_store.load_room("default", "silverbrook.market_square")
    names = {n.name for n in sq.npcs}
    assert "Greta" in names
    assert "Town Guard" in names


def test_graph_persisted(fresh_world):
    starter.seed_world("default")
    g = world_store.load_graph("default")
    assert g["silverbrook.inn"]["north"] == "silverbrook.market_square"
    assert g["silverbrook.market_square"]["east"] == "silverbrook.smithy"
    assert g["silverbrook.market_square"]["west"] == "silverbrook.tavern"
    assert g["silverbrook.market_square"]["north"] == "silverbrook.north_gate"
    assert g["silverbrook.north_gate"]["north"] == "silverbrook.watchtower"


def test_starter_spawn_room_is_inn():
    assert starter.starter_spawn_room("silverbrook") == "silverbrook.inn"
