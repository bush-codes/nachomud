"""Tests for routines.py — projecting NPC presence by game-clock hour."""
from __future__ import annotations

from nachomud.models import NPC
from nachomud.world.routines import hour_from_minute, hour_in_window, npc_location_at, npcs_in_room


def _greta() -> NPC:
    return NPC(
        npc_id="greta", name="Greta", title="Fruit Seller",
        routines=[
            {"start_hr": 6, "end_hr": 17, "location_id": "silverbrook.market_square", "activity": "selling fruit"},
            {"start_hr": 17, "end_hr": 21, "location_id": "silverbrook.tavern", "activity": "drinking"},
            {"start_hr": 21, "end_hr": 30, "location_id": "elsewhere", "activity": "asleep"},
        ],
    )


def test_hour_in_window_simple():
    assert hour_in_window(8, 6, 17)
    assert not hour_in_window(5, 6, 17)
    assert not hour_in_window(17, 6, 17)


def test_hour_in_window_wraps_past_midnight():
    # 22..30 == 22:00 - 06:00 next day
    assert hour_in_window(23, 22, 30)
    assert hour_in_window(2, 22, 30)
    assert hour_in_window(5, 22, 30)
    assert not hour_in_window(7, 22, 30)


def test_npc_location_at_morning():
    g = _greta()
    loc, act = npc_location_at(g, 8)
    assert loc == "silverbrook.market_square"
    assert "selling" in act


def test_npc_location_at_evening():
    g = _greta()
    loc, _ = npc_location_at(g, 19)
    assert loc == "silverbrook.tavern"


def test_npc_location_at_night():
    g = _greta()
    loc, _ = npc_location_at(g, 23)
    assert loc == "elsewhere"


def test_npcs_in_room_filters():
    g = _greta()
    in_market_morning = npcs_in_room([g], "silverbrook.market_square", hour=10)
    assert len(in_market_morning) == 1
    in_market_night = npcs_in_room([g], "silverbrook.market_square", hour=23)
    assert in_market_night == []
    in_tavern_evening = npcs_in_room([g], "silverbrook.tavern", hour=19)
    assert len(in_tavern_evening) == 1


def test_hour_from_minute():
    assert hour_from_minute(0) == 0
    assert hour_from_minute(60) == 1
    assert hour_from_minute(480) == 8
    assert hour_from_minute(1439) == 23
    # Wrap (advancing past 1440 should be normalized by the caller; here just modulo)
    assert hour_from_minute(1500) == 1
