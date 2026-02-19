"""Tests to validate all world JSON files have correct structure and data."""

import json
import os
import pytest

from config import ABILITY_DEFINITIONS

WORLDS_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "worlds")

# Valid mob abilities: anything in ABILITY_DEFINITIONS (which includes "attack")
VALID_MOB_ABILITIES = set(ABILITY_DEFINITIONS.keys())

# Valid item slots
VALID_SLOTS = {"weapon", "armor", "ring"}

# Valid exit directions
VALID_DIRECTIONS = {"n", "s", "e", "w"}
OPPOSITE = {"n": "s", "s": "n", "e": "w", "w": "e"}


def _load_world(world_id: str) -> dict:
    path = os.path.join(WORLDS_DIR, f"{world_id}.json")
    with open(path) as f:
        return json.load(f)


def _all_world_ids():
    """Return list of all world IDs from data/worlds/."""
    ids = []
    for fname in sorted(os.listdir(WORLDS_DIR)):
        if fname.endswith(".json"):
            ids.append(fname[:-5])
    return ids


WORLD_IDS = _all_world_ids()


@pytest.fixture(params=WORLD_IDS)
def world_data(request):
    return request.param, _load_world(request.param)


# ── Structure tests ──────────────────────────────────────────────────


def test_all_worlds_have_meta(world_data):
    world_id, data = world_data
    assert "meta" in data, f"{world_id}: missing 'meta' block"
    assert "name" in data["meta"], f"{world_id}: meta missing 'name'"


def test_all_worlds_have_rooms(world_data):
    world_id, data = world_data
    assert "rooms" in data, f"{world_id}: missing 'rooms' array"
    assert len(data["rooms"]) > 0, f"{world_id}: no rooms"


def test_rooms_have_required_fields(world_data):
    world_id, data = world_data
    for room in data["rooms"]:
        assert "id" in room, f"{world_id}: room missing 'id'"
        assert "name" in room, f"{world_id}/{room.get('id', '?')}: missing 'name'"
        assert "exits" in room, f"{world_id}/{room['id']}: missing 'exits'"


def test_room_ids_are_unique(world_data):
    world_id, data = world_data
    ids = [r["id"] for r in data["rooms"]]
    assert len(ids) == len(set(ids)), f"{world_id}: duplicate room IDs"


# ── Exit tests ───────────────────────────────────────────────────────


def test_exits_use_valid_directions(world_data):
    world_id, data = world_data
    for room in data["rooms"]:
        for direction in room["exits"]:
            assert direction in VALID_DIRECTIONS, (
                f"{world_id}/{room['id']}: invalid direction '{direction}'"
            )


def test_exits_point_to_existing_rooms(world_data):
    world_id, data = world_data
    room_ids = {r["id"] for r in data["rooms"]}
    for room in data["rooms"]:
        for direction, target_id in room["exits"].items():
            assert target_id in room_ids, (
                f"{world_id}/{room['id']}: exit {direction} -> '{target_id}' doesn't exist"
            )


def test_exits_are_bidirectional(world_data):
    world_id, data = world_data
    room_map = {r["id"]: r for r in data["rooms"]}
    for room in data["rooms"]:
        for direction, target_id in room["exits"].items():
            target = room_map[target_id]
            opp = OPPOSITE[direction]
            assert opp in target["exits"], (
                f"{world_id}: {room['id']} -> {direction} -> {target_id}, "
                f"but {target_id} has no {opp} exit back"
            )
            assert target["exits"][opp] == room["id"], (
                f"{world_id}: {room['id']} -> {direction} -> {target_id}, "
                f"but {target_id}.{opp} -> {target['exits'][opp]} (expected {room['id']})"
            )


# ── Mob tests ────────────────────────────────────────────────────────


def test_mobs_have_required_fields(world_data):
    world_id, data = world_data
    for room in data["rooms"]:
        for mob in room.get("mobs", []):
            for field in ("name", "hp", "max_hp", "atk", "mdef", "is_boss"):
                assert field in mob, (
                    f"{world_id}/{room['id']}: mob '{mob.get('name', '?')}' missing '{field}'"
                )


def test_mobs_have_new_fields(world_data):
    """Verify all mobs have the Phase 5 fields: speed, abilities, personality, pdef."""
    world_id, data = world_data
    for room in data["rooms"]:
        for mob in room.get("mobs", []):
            name = mob.get("name", "?")
            assert "speed" in mob, f"{world_id}/{room['id']}: {name} missing 'speed'"
            assert "abilities" in mob, f"{world_id}/{room['id']}: {name} missing 'abilities'"
            assert "personality" in mob, f"{world_id}/{room['id']}: {name} missing 'personality'"
            assert "pdef" in mob, f"{world_id}/{room['id']}: {name} missing 'pdef'"


def test_mob_abilities_are_valid(world_data):
    world_id, data = world_data
    for room in data["rooms"]:
        for mob in room.get("mobs", []):
            for ability in mob.get("abilities", []):
                assert ability in VALID_MOB_ABILITIES, (
                    f"{world_id}/{room['id']}: mob '{mob['name']}' has invalid ability '{ability}'"
                )


def test_mob_hp_positive(world_data):
    world_id, data = world_data
    for room in data["rooms"]:
        for mob in room.get("mobs", []):
            assert mob["hp"] > 0, f"{world_id}: {mob['name']} has hp <= 0"
            assert mob["max_hp"] > 0, f"{world_id}: {mob['name']} has max_hp <= 0"
            assert mob["hp"] <= mob["max_hp"], f"{world_id}: {mob['name']} hp > max_hp"


def test_exactly_one_boss_per_world(world_data):
    world_id, data = world_data
    bosses = []
    for room in data["rooms"]:
        for mob in room.get("mobs", []):
            if mob.get("is_boss"):
                bosses.append(mob["name"])
    assert len(bosses) == 1, f"{world_id}: expected 1 boss, found {len(bosses)}: {bosses}"


def test_bosses_have_multiple_abilities(world_data):
    world_id, data = world_data
    for room in data["rooms"]:
        for mob in room.get("mobs", []):
            if mob.get("is_boss"):
                abilities = mob.get("abilities", [])
                assert len(abilities) >= 3, (
                    f"{world_id}: boss '{mob['name']}' has only {len(abilities)} abilities: {abilities}"
                )


# ── Item tests ───────────────────────────────────────────────────────


def test_items_have_valid_slots(world_data):
    world_id, data = world_data
    for room in data["rooms"]:
        # Ground items
        for item in room.get("items", []):
            assert item.get("slot") in VALID_SLOTS, (
                f"{world_id}/{room['id']}: item '{item.get('name')}' has invalid slot '{item.get('slot')}'"
            )
        # Mob loot
        for mob in room.get("mobs", []):
            for item in mob.get("loot", []):
                assert item.get("slot") in VALID_SLOTS, (
                    f"{world_id}/{room['id']}: loot '{item.get('name')}' has invalid slot '{item.get('slot')}'"
                )
        # NPC items
        for npc in room.get("npcs", []):
            if npc.get("item"):
                item = npc["item"]
                assert item.get("slot") in VALID_SLOTS, (
                    f"{world_id}/{room['id']}: NPC item '{item.get('name')}' has invalid slot '{item.get('slot')}'"
                )


# ── Connectivity test ────────────────────────────────────────────────


def test_all_rooms_reachable(world_data):
    """BFS from room_1 should reach all rooms."""
    world_id, data = world_data
    room_map = {r["id"]: r for r in data["rooms"]}
    start = "room_1" if "room_1" in room_map else data["rooms"][0]["id"]

    visited = set()
    queue = [start]
    while queue:
        current = queue.pop(0)
        if current in visited:
            continue
        visited.add(current)
        for target_id in room_map[current]["exits"].values():
            if target_id not in visited:
                queue.append(target_id)

    unreachable = set(room_map.keys()) - visited
    assert len(unreachable) == 0, (
        f"{world_id}: unreachable rooms from {start}: {unreachable}"
    )
