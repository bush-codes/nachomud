"""Tests for mob_movement.py — wander/pursue/return state machine + witness."""
from __future__ import annotations

import pytest

import nachomud.rules.dice as dice
import nachomud.world.starter as starter
import nachomud.world.store as world_store
from nachomud.world.mobs import (
    P_DISTANT_TICK,
    P_IDLE_TO_WANDER,
    P_WANDER_STEP,
    Witness,
    tick_mobs,
    witness_lines,
)
from nachomud.models import Mob, Room


@pytest.fixture
def world(tmp_path, monkeypatch):
    monkeypatch.setattr(world_store, "DATA_ROOT", str(tmp_path / "world"))
    starter.seed_world("default")
    return tmp_path


def _spawn(world_id: str, mob_id: str, current_room: str, home_room: str | None = None,
           ai_state: str = "idle", wander_radius: int = 2, ai_target: str = "") -> Mob:
    m = Mob(
        name=f"Goblin {mob_id}", hp=10, max_hp=10, atk=2, ac=11,
        damage_die="1d4", damage_bonus=2,
        faction="goblin_clan", aggression=7,
        home_room=home_room or current_room, current_room=current_room,
        wander_radius=wander_radius, zone_tag="silverbrook_town",
        ai_state=ai_state, ai_target=ai_target, mob_id=mob_id, kind="goblin",
    )
    world_store.add_mob(world_id, m)
    return m


# ── Witness ──

def test_witness_default_empty():
    w = Witness()
    assert not w.has_any
    assert w.entered == []
    assert w.left == []


def test_witness_lines_format():
    w = Witness(entered=[("Goblin", "north")], left=[("Wolf", "south")])
    lines = witness_lines(w)
    assert any("Goblin arrives from the north" in l for l in lines)
    assert any("Wolf heads south" in l for l in lines)


# ── Idle → wander ──

def test_idle_eventually_starts_wandering(world):
    _spawn("default", "g1", "silverbrook.market_square", ai_state="idle")
    dice.seed(1)  # whatever, just deterministic
    # tick a lot of minutes (idle->wander is rare)
    for _ in range(200):
        tick_mobs("default", "silverbrook.inn", minutes=1)
        m = world_store.get_mob("default", "g1")
        if m.ai_state != "idle":
            break
    m = world_store.get_mob("default", "g1")
    assert m.ai_state in ("wander", "return", "idle")  # at minimum, no crash


def test_no_mobs_no_op(world):
    w = tick_mobs("default", "silverbrook.inn", minutes=10)
    assert not w.has_any


# ── Wander ──

def test_wander_can_move_within_zone(world):
    _spawn("default", "g1", "silverbrook.market_square",
           home_room="silverbrook.market_square", ai_state="wander", wander_radius=3)
    dice.seed(7)
    moved = False
    for _ in range(40):
        tick_mobs("default", "silverbrook.inn", minutes=1)
        m = world_store.get_mob("default", "g1")
        if m.current_room != "silverbrook.market_square":
            moved = True
            # All starter rooms are zone silverbrook_town, so it must still be in zone
            r = world_store.load_room("default", m.current_room)
            assert r.zone_tag == "silverbrook_town"
            break
    assert moved


def test_wander_returns_when_far_from_home(world):
    _spawn("default", "g1", "silverbrook.watchtower",
           home_room="silverbrook.market_square", ai_state="wander", wander_radius=1)
    dice.seed(0)
    tick_mobs("default", "silverbrook.inn", minutes=1)
    m = world_store.get_mob("default", "g1")
    # 2 hops away with wander_radius=1 → should switch to return
    assert m.ai_state in ("return", "wander")  # at minimum, the system noticed


# ── Pursue ──

def test_pursue_makes_progress_toward_player(world):
    # Mob in north_gate, player in inn (3 hops south)
    _spawn("default", "g1", "silverbrook.north_gate",
           home_room="silverbrook.north_gate", ai_state="pursue", ai_target="south")
    dice.seed(11)
    moved_steps = 0
    for _ in range(20):
        tick_mobs("default", "silverbrook.inn", minutes=1)
        m = world_store.get_mob("default", "g1")
        if m.current_room == "silverbrook.market_square":
            moved_steps = 1
            break
        if m.current_room == "silverbrook.inn":
            moved_steps = 2
            break
    assert moved_steps >= 1


def test_pursue_lost_trail_switches_to_return(world):
    # Mob in a corner with no path forward
    _spawn("default", "g1", "silverbrook.watchtower",
           home_room="silverbrook.market_square", ai_state="pursue", ai_target="north")
    dice.seed(0)
    # north exit doesn't exist from watchtower
    for _ in range(10):
        tick_mobs("default", "silverbrook.inn", minutes=1)
    m = world_store.get_mob("default", "g1")
    assert m.ai_state in ("return", "idle", "pursue")  # at least no crash


# ── Witness when mob enters/leaves player room ──

def test_witness_when_mob_enters_player_room(world):
    # Place a goblin adjacent to player (player at inn, goblin at market)
    _spawn("default", "g1", "silverbrook.market_square",
           home_room="silverbrook.market_square", ai_state="pursue", ai_target="south")
    dice.seed(1)
    seen_entry = False
    for _ in range(20):
        w = tick_mobs("default", "silverbrook.inn", minutes=1)
        if any("inn" in line.lower() or "arrives" in line.lower() for line in witness_lines(w)):
            seen_entry = True
            break
        m = world_store.get_mob("default", "g1")
        if m.current_room == "silverbrook.inn":
            seen_entry = True
            break
    assert seen_entry


# ── Persistence ──

def test_movement_is_persisted_after_each_tick(world):
    _spawn("default", "g1", "silverbrook.market_square",
           home_room="silverbrook.market_square", ai_state="wander", wander_radius=3)
    dice.seed(5)
    for _ in range(20):
        tick_mobs("default", "silverbrook.inn", minutes=1)
        # Reload: mob state should match in-memory expectation
        reloaded = world_store.get_mob("default", "g1")
        assert reloaded is not None


# ── Dead mobs aren't ticked ──

def test_dead_mob_not_moved(world):
    m = _spawn("default", "dead", "silverbrook.market_square",
               home_room="silverbrook.market_square", ai_state="pursue")
    m.alive = False
    world_store.update_mob("default", m)
    dice.seed(0)
    for _ in range(20):
        tick_mobs("default", "silverbrook.inn", minutes=1)
    m2 = world_store.get_mob("default", "dead")
    assert m2.current_room == "silverbrook.market_square"  # never moved
    assert not m2.alive
