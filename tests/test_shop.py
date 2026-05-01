"""Tests for the shop system: gold, wares, buy command."""
from __future__ import annotations

import pytest

import nachomud.characters.save as player_mod
import nachomud.world.starter as starter
import nachomud.world.store as world_store
from nachomud.characters.character import create_character
from nachomud.ai.dm import DM
from nachomud.engine.game import Game
from nachomud.models import NPC
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
    a.room_id = "silverbrook.market_square"  # Greta is here in the morning
    player_mod.save_player(a)
    return a


@pytest.fixture
def game(aric):
    return Game(player=aric,
                dm=DM(llm=lambda s, u: "ok."),
                npc_dialogue=NPCDialogue(llm=lambda s, u: "Aye.", summarizer=lambda s, u: "s."))


def _text(msgs):
    return "".join(m[1] for m in msgs if isinstance(m, tuple) and m[0] == "output")


# ── Starting gold ──

def test_new_character_has_starting_gold(aric):
    from nachomud.settings import STARTING_GOLD
    assert aric.gold == STARTING_GOLD


def test_gold_persists_across_save_and_load(aric):
    aric.gold = 42
    player_mod.save_player(aric)
    p2 = player_mod.load_player("p1")
    assert p2.gold == 42


# ── Wares listing ──

def test_wares_lists_greta_apples(game):
    msgs = game.handle("wares")
    text = _text(msgs)
    assert "Greta" in text
    assert "Red Apple" in text
    assert "2 gp" in text


def test_wares_filters_by_npc(game):
    # Only Greta has wares in market square (Town Guard doesn't sell anything)
    msgs = game.handle("wares greta")
    text = _text(msgs)
    assert "Greta" in text
    assert "Red Apple" in text


def test_wares_no_one_selling_in_inn(game):
    game.player.room_id = "silverbrook.inn"
    game._room = None
    # Marta sells stuff at the inn — make sure those show
    msgs = game.handle("wares")
    text = _text(msgs)
    assert "Marta" in text
    assert "Trail Rations" in text


def test_wares_in_smithy_shows_weapons(game):
    # Move to smithy
    game.handle("east")  # market → smithy
    msgs = game.handle("wares")
    text = _text(msgs)
    assert "Old John" in text
    assert "Steel Shortsword" in text


# ── Buy ──

def test_buy_apple_from_greta(game):
    before = game.player.gold
    msgs = game.handle("buy red apple")
    text = _text(msgs)
    assert "Greta" in text
    assert "Red Apple" in text
    # Gold deducted
    assert game.player.gold == before - 2
    # Item in inventory
    assert any(it.name == "Red Apple" for it in game.player.inventory)
    # And in items.json under inv:p1
    inv = world_store.items_in_inventory("default", "p1")
    assert any(i["name"] == "Red Apple" for i in inv)


def test_buy_with_explicit_npc(game):
    msgs = game.handle("buy honey pear from greta")
    text = _text(msgs)
    assert "Honey Pear" in text


def test_buy_fails_when_too_poor(game):
    # Move to smithy where the shortsword costs 25gp — Aric has 25 starting,
    # so let's drain him first
    game.player.gold = 1
    game.handle("east")
    msgs = game.handle("buy steel shortsword")
    text = _text(msgs)
    assert "afford" in text.lower()
    # Inventory unchanged
    assert not any(it.name == "Steel Shortsword" for it in game.player.inventory)


def test_buy_unknown_item_falls_through_to_dm(game):
    """No matching item from any present shopkeeper → DM adjudicates
    naturally instead of a flat error."""
    msgs = game.handle("buy phlogiston")
    text = _text(msgs)
    assert "DM:" in text


def test_buy_no_seller_in_room_falls_through_to_dm(game):
    """No shopkeeper in the room → DM adjudicates."""
    game.handle("north")  # market → north_gate (no shopkeeper)
    msgs = game.handle("buy apple")
    text = _text(msgs)
    assert "DM:" in text


def test_buy_persists(game):
    game.handle("buy red apple")
    p2 = player_mod.load_player("p1")
    assert p2.gold == game.player.gold
    assert any(it.name == "Red Apple" for it in p2.inventory)


# ── Inventory + prompt show gold ──

def test_inventory_shows_gold(game):
    msgs = game.handle("inventory")
    text = _text(msgs)
    assert "Gold:" in text
    assert "gp" in text


def test_prompt_includes_gold(game):
    msgs = game.handle("look")
    # The prompt is the last message
    prompt_msgs = [m for m in msgs if isinstance(m, tuple) and m[0] == "prompt"]
    assert prompt_msgs
    assert "gp" in prompt_msgs[-1][1]


# ── Drop a bought item leaves it in the room ──

def test_drop_bought_item_lands_in_room(game):
    game.handle("buy red apple")
    msgs = game.handle("drop red apple")
    text = _text(msgs)
    assert "drop" in text.lower()
    # Room now has the item
    in_room = world_store.items_in_room("default", game.player.room_id)
    assert any(i["name"] == "Red Apple" for i in in_room)
