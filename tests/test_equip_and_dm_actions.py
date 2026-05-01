"""Tests for the equip command and the new DM action twins
(get_item, drop_item, equip_item, buy_item).

These complete the harmony pattern: every state-mutating verb has both a
fast deterministic command and a DM-driven natural-language path that
emits a structured action the engine validates and applies.
"""
from __future__ import annotations

import json

import pytest

import nachomud.characters.save as player_mod
import nachomud.world.starter as starter
import nachomud.world.store as world_store
from nachomud.characters.character import create_character
from nachomud.ai.dm import DM
from nachomud.engine.game import Game, _equip_from_inventory
from nachomud.models import Item
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
    a.room_id = "silverbrook.market_square"
    player_mod.save_player(a)
    return a


def _stub_dm():
    return DM(llm=lambda s, u: "ok.")


def _stub_npc():
    return NPCDialogue(llm=lambda s, u: "Aye.", summarizer=lambda s, u: "s.")


def _text(msgs):
    return "".join(m[1] for m in msgs if isinstance(m, tuple) and m[0] == "output")


# ── Fast-path equip command ──

def test_equip_swaps_weapon(aric):
    new_blade = Item(name="Iron Dagger", slot="weapon", damage_die="1d4", finesse=True)
    aric.inventory.append(new_blade)
    old_weapon_name = aric.weapon.name
    g = Game(player=aric, dm=_stub_dm(), npc_dialogue=_stub_npc())
    g.start()
    msgs = g.handle("equip iron dagger")
    assert "equip" in _text(msgs).lower()
    assert aric.weapon.name == "Iron Dagger"
    # Old weapon went back to inventory
    assert any(it.name == old_weapon_name for it in aric.inventory)


def test_equip_armor_recomputes_ac(aric):
    light = Item(name="Spare Robe", slot="armor", armor_base=11, armor_max_dex=None)
    aric.inventory.append(light)
    g = Game(player=aric, dm=_stub_dm(), npc_dialogue=_stub_npc())
    g.start()
    before_ac = aric.ac
    g.handle("equip spare robe")
    # Robe gives base 11 + DEX 13 mod (+1, no cap) = 12. Was 18 (chainmail).
    assert aric.ac == 12
    assert aric.ac != before_ac


def test_equip_class_restricted(aric):
    forbidden = Item(name="Wand of Mage Power", slot="weapon", damage_die="1d4",
                     allowed_classes=["Mage"])
    aric.inventory.append(forbidden)
    g = Game(player=aric, dm=_stub_dm(), npc_dialogue=_stub_npc())
    g.start()
    msgs = g.handle("equip wand")
    text = _text(msgs)
    assert "Mage" in text  # restriction surfaced
    assert aric.weapon.name != "Wand of Mage Power"


def test_equip_missing_item(aric):
    g = Game(player=aric, dm=_stub_dm(), npc_dialogue=_stub_npc())
    g.start()
    msgs = g.handle("equip phlogiston staff")
    text = _text(msgs)
    assert "aren't carrying" in text.lower()


def test_equip_non_equippable_item(aric):
    aric.inventory.append(Item(name="Trail Rations", slot="consumable"))
    g = Game(player=aric, dm=_stub_dm(), npc_dialogue=_stub_npc())
    g.start()
    msgs = g.handle("equip trail rations")
    text = _text(msgs)
    assert "isn't equippable" in text.lower()


def test_wield_alias_works(aric):
    blade = Item(name="Iron Dagger", slot="weapon", damage_die="1d4")
    aric.inventory.append(blade)
    g = Game(player=aric, dm=_stub_dm(), npc_dialogue=_stub_npc())
    g.start()
    g.handle("wield iron dagger")
    assert aric.weapon.name == "Iron Dagger"


def test_wear_alias_works(aric):
    armor = Item(name="Light Tunic", slot="armor", armor_base=11)
    aric.inventory.append(armor)
    g = Game(player=aric, dm=_stub_dm(), npc_dialogue=_stub_npc())
    g.start()
    g.handle("wear light tunic")
    assert aric.armor.name == "Light Tunic"


# ── DM equip_item action ──

def test_dm_equip_item_action(aric):
    blade = Item(name="Iron Dagger", slot="weapon", damage_die="1d4", finesse=True)
    aric.inventory.append(blade)
    dm = DM(llm=lambda s, u: json.dumps({
        "narrate": "You unsheathe the iron dagger and grip it tight.",
        "actions": [{"type": "equip_item", "item_name": "Iron Dagger"}],
    }))
    g = Game(player=aric, dm=dm, npc_dialogue=_stub_npc())
    g.start()
    msgs = g.handle("I switch to my iron dagger")
    text = _text(msgs)
    assert "iron dagger" in text.lower()
    assert "equipped" in text.lower()
    assert aric.weapon.name == "Iron Dagger"


def test_dm_equip_item_validates_inventory(aric):
    """If the DM hallucinates an item the player doesn't have, do nothing."""
    dm = DM(llm=lambda s, u: json.dumps({
        "narrate": "You reach for a sword you don't actually own.",
        "actions": [{"type": "equip_item", "item_name": "Phantom Blade"}],
    }))
    g = Game(player=aric, dm=dm, npc_dialogue=_stub_npc())
    g.start()
    g.handle("I draw the phantom blade")
    # No equipment swap happened
    assert aric.weapon.name == "Longsword"


# ── DM get_item action ──

def test_dm_get_item_action(aric):
    world_store.add_item("default", "herb_1",
                         Item(name="Healing Herb", slot="consumable"),
                         f"room:{aric.room_id}")
    dm = DM(llm=lambda s, u: json.dumps({
        "narrate": "You stoop and pluck the healing herb from the cobbles.",
        "actions": [{"type": "get_item", "item_name": "Healing Herb"}],
    }))
    g = Game(player=aric, dm=dm, npc_dialogue=_stub_npc())
    g.start()
    g.handle("I pick up the herb")
    assert any(it.name == "Healing Herb" for it in aric.inventory)
    # And world entry updated
    inv = world_store.items_in_inventory("default", aric.player_id)
    assert any(i["item_id"] == "herb_1" for i in inv)


def test_dm_get_item_missing_room_item_silent(aric):
    dm = DM(llm=lambda s, u: json.dumps({
        "narrate": "There's nothing to grab.",
        "actions": [{"type": "get_item", "item_name": "Imaginary Gem"}],
    }))
    g = Game(player=aric, dm=dm, npc_dialogue=_stub_npc())
    g.start()
    msgs = g.handle("grab the imaginary gem")
    # No item added
    assert not any(it.name == "Imaginary Gem" for it in aric.inventory)


# ── DM drop_item action ──

def test_dm_drop_item_lands_in_room(aric):
    cheese = Item(name="Cheese Wedge", slot="consumable")
    aric.inventory.append(cheese)
    world_store.add_item("default", "ch_1", cheese, f"inv:{aric.player_id}")
    dm = DM(llm=lambda s, u: json.dumps({
        "narrate": "You toss the cheese onto the cobbles.",
        "actions": [{"type": "drop_item", "item_name": "Cheese Wedge"}],
    }))
    g = Game(player=aric, dm=dm, npc_dialogue=_stub_npc())
    g.start()
    g.handle("I throw away the cheese")
    assert not any(it.name == "Cheese Wedge" for it in aric.inventory)
    in_room = world_store.items_in_room("default", aric.room_id)
    assert any(i["item_id"] == "ch_1" for i in in_room)


# ── DM buy_item action ──

def test_dm_buy_item_action(aric):
    """Aric is in market_square where Greta sells fruit. DM emits buy_item."""
    starting_gold = aric.gold
    dm = DM(llm=lambda s, u: json.dumps({
        "narrate": "You hand Greta two coppers; she hands you a bright red apple.",
        "actions": [{"type": "buy_item", "item_name": "Red Apple",
                     "npc_name": "Greta"}],
    }))
    g = Game(player=aric, dm=dm, npc_dialogue=_stub_npc())
    g.start()
    g.handle("I'd like to buy a red apple from greta")
    assert any(it.name == "Red Apple" for it in aric.inventory)
    assert aric.gold == starting_gold - 2


def test_dm_buy_item_too_poor_silent(aric):
    aric.gold = 0
    dm = DM(llm=lambda s, u: json.dumps({
        "narrate": "Your purse is empty.",
        "actions": [{"type": "buy_item", "item_name": "Red Apple",
                     "npc_name": "Greta"}],
    }))
    g = Game(player=aric, dm=dm, npc_dialogue=_stub_npc())
    g.start()
    g.handle("I want the apple")
    # Validator rejected: no item, gold unchanged
    assert not any(it.name == "Red Apple" for it in aric.inventory)
    assert aric.gold == 0


def test_dm_buy_item_no_shopkeeper_silent(aric):
    aric.room_id = "silverbrook.inn"
    aric._room = None
    dm = DM(llm=lambda s, u: json.dumps({
        "narrate": "The hearth crackles — there's no fruit stall here.",
        "actions": [{"type": "buy_item", "item_name": "Red Apple",
                     "npc_name": "Greta"}],
    }))
    g = Game(player=aric, dm=dm, npc_dialogue=_stub_npc())
    g.start()
    g.handle("buy an apple")
    # No transaction — Greta isn't here
    assert not any(it.name == "Red Apple" for it in aric.inventory)


# ── _equip_from_inventory helper directly ──

def test_equip_helper_returns_failure_for_missing(aric):
    out = _equip_from_inventory(aric, "nothing")
    assert not out["ok"]
    assert "carrying" in out["message"].lower()


def test_equip_helper_replaces_old_into_inventory(aric):
    blade = Item(name="Steel Shortsword", slot="weapon", damage_die="1d6", finesse=True)
    aric.inventory.append(blade)
    out = _equip_from_inventory(aric, "shortsword")
    assert out["ok"]
    assert aric.weapon.name == "Steel Shortsword"
    # Old longsword went into inventory
    assert any(it.name == "Longsword" for it in aric.inventory)
