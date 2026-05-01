"""Player save/load.

One file per player at `data/players/<player_id>.json`. The file holds the
full AgentState (including stats, inventory, equipment, dm_context, game
clock). Inventory items are inlined; world-resident items live in
`world_store.items.json` keyed by item_id.

The schema is versioned so future migrations can walk old saves forward.
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, fields
from typing import Any

from nachomud.characters.migrations import migrate
from nachomud.models import AgentState, Item, StatusEffect

SCHEMA_VERSION_PLAYER = 1

DATA_ROOT = os.environ.get("NACHOMUD_PLAYERS_ROOT", os.path.join("data", "players"))


def _ensure_root() -> None:
    os.makedirs(DATA_ROOT, exist_ok=True)


def player_path(player_id: str) -> str:
    return os.path.join(DATA_ROOT, f"{player_id}.json")


def _atomic_write_json(path: str, payload: Any) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(payload, f, indent=2, sort_keys=False)
    os.replace(tmp, path)


def _item_to_dict(item: Item | None) -> dict | None:
    return asdict(item) if item is not None else None


def _item_from_dict(d: dict | None) -> Item | None:
    if d is None:
        return None
    field_names = {f.name for f in fields(Item)}
    return Item(**{k: v for k, v in d.items() if k in field_names})


def _effect_from_dict(d: dict) -> StatusEffect:
    return StatusEffect(**d)


def player_to_dict(p: AgentState) -> dict:
    return {
        "player_id": p.player_id,
        "owner_id": None,  # reserved for future auth
        "name": p.name,
        "race": p.race,
        "class": p.agent_class,
        "personality": p.personality,
        "level": p.level,
        "xp": p.xp,
        "stats": dict(p.stats),
        "save_proficiencies": list(p.save_proficiencies),
        "abilities": list(p.abilities),
        "hit_die": p.hit_die,
        "proficiency_bonus": p.proficiency_bonus,
        "hp": p.hp, "max_hp": p.max_hp,
        "mp": p.mp, "max_mp": p.max_mp,
        "ap": p.ap, "max_ap": p.max_ap,
        "ac": p.ac,
        "speed": p.speed,
        "alive": p.alive,
        "status_effects": [asdict(e) for e in p.status_effects],
        "inventory": [_item_to_dict(i) for i in p.inventory],
        "equipment": {
            "weapon": _item_to_dict(p.weapon),
            "armor": _item_to_dict(p.armor),
            "ring": _item_to_dict(p.ring),
            "shield": _item_to_dict(p.shield),
        },
        "current_room": p.room_id,
        "respawn_room": p.respawn_room,
        "world_id": p.world_id,
        "game_clock": dict(p.game_clock),
        "gold": p.gold,
        "dm_context": {
            "recent_exchanges": list(p.dm_context.get("recent_exchanges", [])),
            "summary": p.dm_context.get("summary", ""),
            "pending_hints": list(p.dm_context.get("pending_hints", [])),
            "npc_chats": dict(p.dm_context.get("npc_chats", {})),
        },
        "visited_rooms": list(p.visited_rooms),
        "schema_version": SCHEMA_VERSION_PLAYER,
    }


def player_from_dict(d: dict) -> AgentState:
    d = migrate("player", dict(d), SCHEMA_VERSION_PLAYER)

    eq = d.get("equipment", {})
    weapon = _item_from_dict(eq.get("weapon")) or Item(name="Unarmed", slot="weapon")
    armor = _item_from_dict(eq.get("armor")) or Item(name="Clothes", slot="armor")
    ring = _item_from_dict(eq.get("ring")) or Item(name="Plain Ring", slot="ring")
    shield = _item_from_dict(eq.get("shield"))

    return AgentState(
        name=d["name"],
        personality=d.get("personality", ""),
        agent_class=d["class"],
        race=d.get("race", "Human"),
        level=d.get("level", 1),
        xp=d.get("xp", 0),
        stats=dict(d.get("stats", {})),
        save_proficiencies=list(d.get("save_proficiencies", [])),
        abilities=list(d.get("abilities", [])),
        hit_die=d.get("hit_die", 8),
        proficiency_bonus=d.get("proficiency_bonus", 2),
        hp=d.get("hp", 1),
        max_hp=d.get("max_hp", 1),
        mp=d.get("mp", 0),
        max_mp=d.get("max_mp", 0),
        ap=d.get("ap", 0),
        max_ap=d.get("max_ap", 0),
        ac=d.get("ac", 10),
        speed=d.get("speed", 3),
        alive=d.get("alive", True),
        status_effects=[_effect_from_dict(e) for e in d.get("status_effects", [])],
        inventory=[_item_from_dict(i) for i in d.get("inventory", []) if i is not None],
        weapon=weapon,
        armor=armor,
        ring=ring,
        shield=shield,
        room_id=d.get("current_room", ""),
        respawn_room=d.get("respawn_room", ""),
        world_id=d.get("world_id", "default"),
        player_id=d["player_id"],
        game_clock=dict(d.get("game_clock", {"day": 1, "minute": 480})),
        dm_context=dict(d.get("dm_context", {"recent_exchanges": [], "summary": "", "pending_hints": []})),
        visited_rooms=list(d.get("visited_rooms", [])),
        gold=int(d.get("gold", 0)),
    )


# ── Public API ──

def save_player(p: AgentState) -> None:
    _ensure_root()
    _atomic_write_json(player_path(p.player_id), player_to_dict(p))


def load_player(player_id: str) -> AgentState:
    path = player_path(player_id)
    with open(path) as f:
        return player_from_dict(json.load(f))


def player_exists(player_id: str) -> bool:
    return os.path.isfile(player_path(player_id))


def list_players() -> list[dict]:
    """Return a summary of all saved players: id, name, race, class, level."""
    _ensure_root()
    out = []
    for f in sorted(os.listdir(DATA_ROOT)):
        if not f.endswith(".json"):
            continue
        try:
            with open(os.path.join(DATA_ROOT, f)) as fp:
                d = json.load(fp)
            out.append({
                "player_id": d["player_id"],
                "name": d["name"],
                "race": d.get("race", "?"),
                "class": d.get("class", "?"),
                "level": d.get("level", 1),
            })
        except (KeyError, json.JSONDecodeError):
            continue
    return out


def delete_player(player_id: str) -> bool:
    path = player_path(player_id)
    if os.path.isfile(path):
        os.remove(path)
        return True
    return False
