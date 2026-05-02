"""Tests for player.py and world_store.py — round-trip save/load,
mob/item/room mutability, atomicity."""
from __future__ import annotations

import os

import pytest

import nachomud.characters.save as player_mod
import nachomud.world.store as world_store
from nachomud.characters.character import create_character
from nachomud.models import Item, Mob, NPC, Room, StatusEffect
from nachomud.rules.stats import Stats


@pytest.fixture
def tmp_data_dirs(tmp_path, monkeypatch):
    """Redirect both data roots to a tmp directory for isolation."""
    world_root = tmp_path / "world"
    players_root = tmp_path / "players"
    monkeypatch.setattr(world_store, "DATA_ROOT", str(world_root))
    monkeypatch.setattr(player_mod, "DATA_ROOT", str(players_root))
    return tmp_path


# ── Player round-trip ──

def test_player_round_trip(tmp_data_dirs):
    s = Stats(STR=15, DEX=12, CON=14, INT=8, WIS=10, CHA=13)
    p = create_character("Aric", "Dwarf", "Warrior", s,
                         player_id="player-1",
                         respawn_room="silverbrook.inn",
                         world_id="default")
    p.room_id = "silverbrook.market_square"
    p.inventory.append(Item(name="Healing Potion", slot="consumable"))
    p.status_effects.append(StatusEffect(name="rallied", source="Sera", remaining_ticks=-1, value=2))
    p.dm_context["recent_exchanges"].append({"player": "where am i?", "dm": "you stand in silverbrook"})
    p.dm_context["summary"] = "Aric arrived in Silverbrook this morning."

    player_mod.save_player(p)
    p2 = player_mod.load_player("player-1")

    assert p2.name == "Aric"
    assert p2.race == "Dwarf"
    assert p2.agent_class == "Warrior"
    assert p2.hp == p.hp
    assert p2.max_hp == p.max_hp
    assert p2.ac == p.ac
    assert p2.stats == p.stats
    assert p2.weapon.name == "Longsword"
    assert p2.weapon.damage_die == "1d8"
    assert p2.armor.name == "Chainmail"
    assert len(p2.inventory) == 1
    assert p2.inventory[0].name == "Healing Potion"
    assert len(p2.status_effects) == 1
    assert p2.status_effects[0].name == "rallied"
    assert p2.dm_context["summary"] == "Aric arrived in Silverbrook this morning."
    assert p2.room_id == "silverbrook.market_square"
    assert p2.respawn_room == "silverbrook.inn"


def test_player_exists_and_delete(tmp_data_dirs):
    s = Stats(STR=15, DEX=12, CON=14, INT=8, WIS=10, CHA=13)
    p = create_character("Aric", "Dwarf", "Warrior", s, player_id="player-1")
    assert not player_mod.player_exists("player-1")
    player_mod.save_player(p)
    assert player_mod.player_exists("player-1")
    assert player_mod.delete_player("player-1")
    assert not player_mod.player_exists("player-1")


def test_list_players(tmp_data_dirs):
    s = Stats(STR=15, DEX=12, CON=14, INT=8, WIS=10, CHA=13)
    p1 = create_character("Aric", "Dwarf", "Warrior", s, player_id="p1")
    p2 = create_character("Lyria", "Elf", "Mage", s, player_id="p2")
    player_mod.save_player(p1)
    player_mod.save_player(p2)
    listed = player_mod.list_players()
    ids = {x["player_id"] for x in listed}
    assert ids == {"p1", "p2"}
    by_id = {x["player_id"]: x for x in listed}
    assert by_id["p1"]["race"] == "Dwarf"
    assert by_id["p2"]["class"] == "Mage"


# ── World init ──

def test_init_world_creates_skeleton(tmp_data_dirs):
    world_store.init_world("default", seed=123, theme="forest")
    assert os.path.isfile(world_store.meta_path("default"))
    assert os.path.isfile(world_store.mobs_path("default"))
    assert os.path.isfile(world_store.items_path("default"))
    assert os.path.isfile(world_store.graph_path("default"))
    assert os.path.isdir(world_store.rooms_dir("default"))
    meta = world_store.load_meta("default")
    assert meta["seed"] == 123
    assert meta["theme"] == "forest"
    assert "created_at" in meta


# ── Room round-trip ──

def test_room_round_trip(tmp_data_dirs):
    world_store.init_world("default")
    npc = NPC(name="Greta", title="Fruit Seller", personality="cheerful",
              routines=[{"start_hr": 6, "end_hr": 17, "location_id": "market", "activity": "sells fruit"}])
    room = Room(
        id="silverbrook.market_square",
        name="Market Square",
        description="Bustling stalls and copper roofs.",
        exits={"north": "silverbrook.watchtower", "east": "silverbrook.smithy"},
        zone_tag="silverbrook_town",
        npcs=[npc],
        flags={"festival_active": False},
    )
    world_store.save_room("default", room)

    assert world_store.room_exists("default", "silverbrook.market_square")
    r2 = world_store.load_room("default", "silverbrook.market_square")
    assert r2.id == room.id
    assert r2.description == room.description
    assert r2.exits == room.exits
    assert r2.zone_tag == "silverbrook_town"
    assert len(r2.npcs) == 1
    assert r2.npcs[0].name == "Greta"
    assert r2.npcs[0].routines[0]["start_hr"] == 6
    assert r2.flags == {"festival_active": False}


def test_room_flag_update(tmp_data_dirs):
    world_store.init_world("default")
    room = Room(id="r1", name="Foyer", flags={"door_locked": True})
    world_store.save_room("default", room)
    world_store.update_room_flags("default", "r1", {"door_locked": False, "secret_revealed": True})
    r2 = world_store.load_room("default", "r1")
    assert r2.flags == {"door_locked": False, "secret_revealed": True}


def test_list_rooms(tmp_data_dirs):
    world_store.init_world("default")
    for rid in ["a", "b", "c"]:
        world_store.save_room("default", Room(id=rid, name=rid))
    assert world_store.list_rooms("default") == ["a", "b", "c"]


# ── Mob registry ──

def test_mob_registry(tmp_data_dirs):
    world_store.init_world("default")
    mob = Mob(
        name="Ash Goblin", hp=12, max_hp=12, atk=4, ac=12, level=1,
        stats={"STR": 12, "DEX": 14, "CON": 12, "INT": 6, "WIS": 8, "CHA": 6},
        damage_die="1d6", damage_bonus=2,
        faction="goblin_clan", aggression=7,
        home_room="ember_caves.entrance", current_room="ember_caves.entrance",
        wander_radius=2, zone_tag="ember_caves",
        ai_state="idle", mob_id="ash_goblin_1", kind="ash_goblin",
    )
    world_store.add_mob("default", mob)

    fetched = world_store.get_mob("default", "ash_goblin_1")
    assert fetched is not None
    assert fetched.name == "Ash Goblin"
    assert fetched.faction == "goblin_clan"
    assert fetched.zone_tag == "ember_caves"
    assert fetched.stats["DEX"] == 14

    # Move the mob and persist
    fetched.current_room = "ember_caves.tunnel"
    fetched.ai_state = "wander"
    world_store.update_mob("default", fetched)
    fetched2 = world_store.get_mob("default", "ash_goblin_1")
    assert fetched2.current_room == "ember_caves.tunnel"
    assert fetched2.ai_state == "wander"


def test_mobs_in_room_and_zone(tmp_data_dirs):
    world_store.init_world("default")
    m1 = Mob(name="A", hp=5, max_hp=5, atk=1, mob_id="a", current_room="r1", zone_tag="z1")
    m2 = Mob(name="B", hp=5, max_hp=5, atk=1, mob_id="b", current_room="r1", zone_tag="z1")
    m3 = Mob(name="C", hp=5, max_hp=5, atk=1, mob_id="c", current_room="r2", zone_tag="z1")
    m4 = Mob(name="D", hp=0, max_hp=5, atk=1, mob_id="d", current_room="r1", zone_tag="z1", alive=False)
    for m in (m1, m2, m3, m4):
        world_store.add_mob("default", m)

    in_r1 = world_store.mobs_in_room("default", "r1")
    assert {m.mob_id for m in in_r1} == {"a", "b"}  # d is dead

    in_r1_with_dead = world_store.mobs_in_room("default", "r1", alive_only=False)
    assert {m.mob_id for m in in_r1_with_dead} == {"a", "b", "d"}

    in_z1 = world_store.living_mobs_in_zone("default", "z1")
    assert {m.mob_id for m in in_z1} == {"a", "b", "c"}


# ── Item registry ──

def test_item_registry(tmp_data_dirs):
    world_store.init_world("default")
    sword = Item(name="Short Sword", slot="weapon", damage_die="1d6")
    world_store.add_item("default", "sword_1", sword, "room:silverbrook.smithy")

    fetched = world_store.get_item("default", "sword_1")
    assert fetched is not None
    assert fetched["name"] == "Short Sword"
    assert fetched["location"] == "room:silverbrook.smithy"

    # Move into player inventory
    world_store.update_item_location("default", "sword_1", "inv:player-1")
    in_smithy = world_store.items_in_room("default", "silverbrook.smithy")
    assert in_smithy == []
    in_inv = world_store.items_in_inventory("default", "player-1")
    assert len(in_inv) == 1 and in_inv[0]["item_id"] == "sword_1"


def test_update_unknown_item_raises(tmp_data_dirs):
    world_store.init_world("default")
    with pytest.raises(KeyError):
        world_store.update_item_location("default", "nope", "room:r1")


# ── Graph ──

def test_graph_add_edge_bidirectional(tmp_data_dirs):
    world_store.init_world("default")
    world_store.add_edge("default", "r1", "north", "r2")
    g = world_store.load_graph("default")
    assert g["r1"]["north"] == "r2"
    assert g["r2"]["south"] == "r1"


def test_graph_add_edge_one_way(tmp_data_dirs):
    world_store.init_world("default")
    world_store.add_edge("default", "r1", "down", "pit", bidirectional=False)
    g = world_store.load_graph("default")
    assert g["r1"]["down"] == "pit"
    assert "pit" not in g  # no return edge


# ── Composite scenario per Phase 2 done-when ──

def test_round_trip_player_plus_3_rooms_plus_mobs_plus_items(tmp_data_dirs):
    """Phase 2 done-when: player + 3 rooms + 5 mobs + 3 items, mob mid-zone, item in inventory."""
    world_store.init_world("default", seed=42)

    # 3 rooms
    for rid in ["silverbrook.inn", "silverbrook.market_square", "silverbrook.smithy"]:
        world_store.save_room("default", Room(id=rid, name=rid.split(".")[-1].title(),
                                              zone_tag="silverbrook_town"))
    world_store.add_edge("default", "silverbrook.inn", "north", "silverbrook.market_square")
    world_store.add_edge("default", "silverbrook.market_square", "east", "silverbrook.smithy")

    # 5 mobs (one starts wandering elsewhere)
    for i in range(5):
        m = Mob(
            name=f"Goblin {i}", hp=8, max_hp=8, atk=2, ac=11, level=1,
            mob_id=f"goblin_{i}", kind="goblin",
            home_room="ember_caves.entrance",
            current_room="ember_caves.tunnel" if i == 2 else "ember_caves.entrance",
            zone_tag="ember_caves", faction="goblin_clan",
            ai_state="wander" if i == 2 else "idle",
        )
        world_store.add_mob("default", m)

    # 3 items: sword in room, robe in room, potion in inventory
    world_store.add_item("default", "sword_1",
                         Item(name="Short Sword", slot="weapon", damage_die="1d6"),
                         "room:silverbrook.smithy")
    world_store.add_item("default", "robe_1",
                         Item(name="Spare Robe", slot="armor", armor_base=11),
                         "room:silverbrook.market_square")
    world_store.add_item("default", "potion_1",
                         Item(name="Healing Potion", slot="consumable"),
                         "inv:player-1")

    # Player
    s = Stats(STR=15, DEX=12, CON=14, INT=8, WIS=10, CHA=13)
    p = create_character("Aric", "Dwarf", "Warrior", s, player_id="player-1",
                         respawn_room="silverbrook.inn", world_id="default")
    p.room_id = "silverbrook.inn"
    player_mod.save_player(p)

    # Reload everything
    rooms = [world_store.load_room("default", r) for r in world_store.list_rooms("default")]
    assert len(rooms) == 3

    mobs = world_store.load_mobs("default")
    assert len(mobs) == 5
    assert mobs["goblin_2"].current_room == "ember_caves.tunnel"
    assert mobs["goblin_2"].ai_state == "wander"

    smithy_items = world_store.items_in_room("default", "silverbrook.smithy")
    assert [i["item_id"] for i in smithy_items] == ["sword_1"]
    inv = world_store.items_in_inventory("default", "player-1")
    assert [i["item_id"] for i in inv] == ["potion_1"]

    p2 = player_mod.load_player("player-1")
    assert p2.name == "Aric"
    assert p2.world_id == "default"
    assert p2.respawn_room == "silverbrook.inn"

    g = world_store.load_graph("default")
    assert g["silverbrook.market_square"]["south"] == "silverbrook.inn"


# ── Migration framework ──

def test_migration_no_op_for_current_version():
    from nachomud.characters.migrations import migrate
    payload = {"schema_version": 1, "x": "y"}
    out = migrate("anything", payload, target_version=1)
    assert out == payload


def test_migration_raises_when_no_path_registered():
    from nachomud.characters.migrations import migrate
    with pytest.raises(ValueError):
        migrate("unknown_entity", {"schema_version": 0}, target_version=1)


def test_dm_ollama_url_round_trip(tmp_data_dirs):
    """Per-character DM-tier Ollama URL persists across save/load."""
    s = Stats(STR=15, DEX=12, CON=14, INT=8, WIS=10, CHA=13)
    p = create_character("Aric", "Dwarf", "Warrior", s, player_id="player-1")
    p.dm_ollama_url = "http://100.67.248.3:11434"
    player_mod.save_player(p)
    p2 = player_mod.load_player("player-1")
    assert p2.dm_ollama_url == "http://100.67.248.3:11434"


def test_v1_player_save_loads_with_empty_dm_url(tmp_data_dirs):
    """Pre-v2 saves (no dm_ollama_url field) load with the field
    defaulted to empty — not a load failure."""
    import json
    s = Stats(STR=15, DEX=12, CON=14, INT=8, WIS=10, CHA=13)
    p = create_character("Aric", "Dwarf", "Warrior", s, player_id="player-1")
    player_mod.save_player(p)
    path = player_mod.player_path("player-1")
    with open(path) as f:
        payload = json.load(f)
    payload["schema_version"] = 1
    payload.pop("dm_ollama_url", None)
    with open(path, "w") as f:
        json.dump(payload, f)

    p2 = player_mod.load_player("player-1")
    assert p2.name == "Aric"
    assert p2.dm_ollama_url == ""
