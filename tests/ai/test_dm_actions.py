"""Tests for DM-requested state actions (consume_item, restore_hp, set_flag).

The DM can request engine-validated state changes via its adjudicate output;
the engine applies them deterministically with bounds and validation.
"""
from __future__ import annotations

import json

import pytest

import nachomud.characters.save as player_mod
import nachomud.world.starter as starter
import nachomud.world.store as world_store
from nachomud.characters.character import create_character
from nachomud.ai.dm import DM
from nachomud.models import Item, Room
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
    return a


def _llm_returning(payload: dict):
    return lambda system, user: json.dumps(payload)


def _room():
    return Room(id="r1", name="Library", description="Dusty books.", exits={"south": "x"})


# ── consume_item ──

def test_consume_item_removes_from_inventory(aric):
    aric.inventory.append(Item(name="Red Apple", slot="consumable"))
    dm = DM(llm=_llm_returning({
        "narrate": "Crisp and sweet.",
        "actions": [{"type": "consume_item", "item_name": "Red Apple"}],
    }))
    out = dm.adjudicate(aric, _room(), "I eat my red apple")
    assert any(it.name == "Red Apple" for it in aric.inventory) is False
    applied = out["actions_applied"]
    assert any(a["type"] == "consumed" and a["item"] == "Red Apple" for a in applied)


def test_consume_item_marks_world_store_consumed(aric):
    # Mint a world item entry like buy would
    world_store.add_item("default", "shop_apple_1",
                         Item(name="Red Apple", slot="consumable"),
                         f"inv:{aric.player_id}")
    aric.inventory.append(Item(name="Red Apple", slot="consumable"))
    dm = DM(llm=_llm_returning({
        "narrate": "Crisp and sweet.",
        "actions": [{"type": "consume_item", "item_name": "Red Apple"}],
    }))
    dm.adjudicate(aric, _room(), "eat the apple")
    # World store entry should now be at location 'consumed'
    entry = world_store.get_item("default", "shop_apple_1")
    assert entry["location"] == "consumed"
    # Not in inventory queries any more
    assert world_store.items_in_inventory("default", aric.player_id) == []


def test_consume_item_player_doesnt_have_it_is_silent(aric):
    """LLM hallucinates an item — engine just ignores it."""
    dm = DM(llm=_llm_returning({
        "narrate": "You try to nibble a phantom biscuit.",
        "actions": [{"type": "consume_item", "item_name": "Phantom Biscuit"}],
    }))
    out = dm.adjudicate(aric, _room(), "I eat my phantom biscuit")
    assert out["actions_applied"] == []


# ── restore_hp / mp / ap (bounded) ──

def test_restore_hp_increases_hp(aric):
    aric.hp = 5
    dm = DM(llm=_llm_returning({
        "narrate": "It nourishes you.",
        "actions": [{"type": "restore_hp", "amount": 2}],
    }))
    out = dm.adjudicate(aric, _room(), "I eat the loaf")
    assert aric.hp == 7
    assert any(a["type"] == "restored" and a["amount"] == 2 for a in out["actions_applied"])


def test_restore_hp_capped_at_5(aric):
    aric.hp = 1
    dm = DM(llm=_llm_returning({
        "narrate": "Suspiciously potent.",
        "actions": [{"type": "restore_hp", "amount": 999}],
    }))
    dm.adjudicate(aric, _room(), "drink the suspiciously potent elixir")
    # Hard cap is 5
    assert aric.hp == 6


def test_restore_hp_capped_at_max(aric):
    """Even within the +5 cap, can't exceed max_hp."""
    aric.hp = aric.max_hp - 1
    dm = DM(llm=_llm_returning({
        "narrate": "ok",
        "actions": [{"type": "restore_hp", "amount": 5}],
    }))
    dm.adjudicate(aric, _room(), "x")
    assert aric.hp == aric.max_hp


def test_restore_at_full_hp_is_noop(aric):
    aric.hp = aric.max_hp
    dm = DM(llm=_llm_returning({
        "narrate": "Already brimming.",
        "actions": [{"type": "restore_hp", "amount": 3}],
    }))
    out = dm.adjudicate(aric, _room(), "x")
    # No action recorded since nothing actually changed
    assert out["actions_applied"] == []


def test_restore_mp_works(aric):
    # Aric is a Warrior (no MP), use a Mage instead
    s = Stats(STR=8, DEX=14, CON=12, INT=15, WIS=13, CHA=10)
    lyria = create_character("Lyria", "Human", "Mage", s, player_id="p2", world_id="default")
    lyria.mp = 5
    dm = DM(llm=_llm_returning({
        "narrate": "Mana coils through you.",
        "actions": [{"type": "restore_mp", "amount": 3}],
    }))
    dm.adjudicate(lyria, _room(), "I sip the mana potion")
    assert lyria.mp == 8


# ── set_flag ──

def test_set_flag_persists_to_room(aric, world):
    room = world_store.load_room("default", "silverbrook.inn")
    dm = DM(llm=_llm_returning({
        "narrate": "The hidden hatch slides open.",
        "skill_check": None,
        "actions": [{"type": "set_flag", "flag": "hidden_hatch_open", "value": True}],
    }))
    dm.adjudicate(aric, room, "I pry up the floorboard near the hearth")
    # In-memory + persisted
    assert room.flags.get("hidden_hatch_open") is True
    reloaded = world_store.load_room("default", "silverbrook.inn")
    assert reloaded.flags.get("hidden_hatch_open") is True


def test_set_flag_rejects_garbage_names(aric):
    room = _room()
    dm = DM(llm=_llm_returning({
        "narrate": "ok",
        "actions": [{"type": "set_flag", "flag": "bad name with spaces!", "value": True}],
    }))
    dm.adjudicate(aric, room, "x")
    assert "bad name with spaces!" not in room.flags


# ── Gating: actions only run on skill-check success ──

def test_actions_blocked_when_skill_check_fails(aric):
    import nachomud.rules.dice as _dice
    _dice.seed(7)  # whatever — we'll force a low DC via prompt, see below

    # Use a DC the player can't make: DC 30 vs +3 STR mod
    dm = DM(llm=_llm_returning({
        "narrate": "You strain at the boulder.",
        "skill_check": {"stat": "STR", "dc": 30,
                        "on_success": "It rolls aside.",
                        "on_fail": "It refuses."},
        "actions": [{"type": "set_flag", "flag": "boulder_moved", "value": True}],
    }))
    room = _room()
    out = dm.adjudicate(aric, room, "I push the boulder")
    assert out["skill_check_result"]["success"] is False
    # Flag should NOT have been set because the gate failed
    assert "boulder_moved" not in room.flags
    assert out["actions_applied"] == []


def test_actions_run_when_skill_check_succeeds(aric):
    # DC 5 vs +3 STR mod — can only fail on a nat 1
    dm = DM(llm=_llm_returning({
        "narrate": "You shoulder the bookcase aside.",
        "skill_check": {"stat": "STR", "dc": 5,
                        "on_success": "It scrapes open, revealing a stair.",
                        "on_fail": "It barely budges."},
        "actions": [{"type": "set_flag", "flag": "secret_stair", "value": True}],
    }))
    room = _room()
    # Loop a couple of times to avoid the rare nat-1 fail
    for _ in range(5):
        if "secret_stair" in room.flags:
            break
        room.flags = {}
        dm.adjudicate(aric, room, "push the bookcase")
    assert room.flags.get("secret_stair") is True


# ── Multiple actions in one adjudicate ──

def test_multiple_actions_apply_in_order(aric):
    aric.inventory.append(Item(name="Healing Potion", slot="consumable"))
    aric.hp = 5
    dm = DM(llm=_llm_returning({
        "narrate": "Warm light blooms in your chest.",
        "actions": [
            {"type": "consume_item", "item_name": "Healing Potion"},
            {"type": "restore_hp", "amount": 5},
        ],
    }))
    out = dm.adjudicate(aric, _room(), "drink the healing potion")
    types = [a["type"] for a in out["actions_applied"]]
    assert types == ["consumed", "restored"]
    assert not any(it.name == "Healing Potion" for it in aric.inventory)
    assert aric.hp == 10


def test_unknown_action_type_ignored(aric):
    dm = DM(llm=_llm_returning({
        "narrate": "ok",
        "actions": [{"type": "give_player_a_billion_gold"}],
    }))
    out = dm.adjudicate(aric, _room(), "I demand riches")
    assert out["actions_applied"] == []
