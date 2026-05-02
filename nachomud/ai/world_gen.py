"""DM-driven procedural room generation.

Triggered when a player crosses an unexplored exit. The LLM emits a JSON
payload describing the next room (name, description, exits, NPCs, mobs,
items); we parse it, persist the room across the world stores, and
return the materialized Room.

Held by the DM as a delegate (`DM.world_gen`); also exported as
`generate_room` for non-DM callers (the agent runner currently goes
through DM, but a future caller could bypass).
"""
from __future__ import annotations

import json
import logging
import re
import uuid
from collections.abc import Callable
from dataclasses import dataclass

import nachomud.world.store as world_store
from nachomud.ai.contexts import load as load_context
from nachomud.ai.llm import LLMUnavailable
from nachomud.models import Item, Mob, NPC, Room
from nachomud.world.directions import VALID_DIRS, opposite

log = logging.getLogger("nachomud.world_gen")

LLMFn = Callable[[str, str], str]
"""(system_prompt, user_prompt) -> reply"""


ROOM_GEN_PERSONA = load_context("dm_room_gen")


def _build_room_gen_prompt(source: Room, direction: str) -> str:
    return (
        f"The player just moved {direction} from this room:\n"
        f"  Source room: {source.name} ({source.id})\n"
        f"  Source zone: {source.zone_tag or 'unknown'}\n"
        f"  Source description: {source.description}\n\n"
        f"Generate the next room in JSON, with this exact schema:\n"
        f"{{\n"
        f"  \"name\": \"<short evocative name>\",\n"
        f"  \"description\": \"<2-4 sentences, what the player sees>\",\n"
        f"  \"zone_tag\": \"<zone identifier, often same as source>\",\n"
        f"  \"exits\": [\"<direction>\", ...],            // REQUIRED — 1-2 forward exits (north/south/east/west/up/down). MUST NOT be empty.\n"
        f"  \"npcs\": [{{\"name\": \"...\", \"title\": \"...\", \"personality\": \"...\", \"faction\": \"...\", \"routines\": [{{\"start_hr\": 0, \"end_hr\": 24, \"location_id\": \"this_room\", \"activity\": \"...\"}}], \"lore\": [\"<fact 1>\", \"<fact 2>\", \"<fact 3>\"]}}],\n"
        f"  \"mobs\": [{{\"name\": \"...\", \"hp\": 8, \"ac\": 11, \"stats\": {{\"STR\": 10, \"DEX\": 14, \"CON\": 10, \"INT\": 6, \"WIS\": 8, \"CHA\": 6}}, \"damage_die\": \"1d6\", \"damage_bonus\": 2, \"faction\": \"...\", \"aggression\": 6, \"xp_value\": 75}}],   // xp_value 50-150 for early-area mobs; bigger threats give more\n"
        f"  \"items\": [{{\"name\": \"...\", \"slot\": \"weapon|armor|ring|consumable\"}}]\n"
        f"}}\n\n"
        f"Return ONLY the JSON object."
    )


_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


def _extract_json(text: str) -> dict:
    """Find the first JSON object in `text` and parse it."""
    if not text:
        raise ValueError("empty LLM output")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    m = _JSON_RE.search(text)
    if not m:
        raise ValueError(f"no JSON object found in output: {text[:200]!r}")
    return json.loads(m.group(0))


def _allocate_room_id(zone_tag: str) -> str:
    z = zone_tag or "wild"
    return f"{z}.{uuid.uuid4().hex[:10]}"


@dataclass
class WorldGen:
    """LLM-driven room generator. One instance per DM."""
    llm: LLMFn

    def generate_room(self, source: Room, direction: str, world_id: str,
                      *, requested_id: str | None = None,
                      max_retries: int = 2) -> Room:
        """Generate a new room and persist it across all three stores.

        Idempotent on `requested_id`: if a room with that id already
        exists (another actor raced ahead and created it on their own
        GPU), skip the LLM round-trip and return the existing room.
        This is belt-and-suspenders — the WorldLoop._lock currently
        serializes _cmd_move so two concurrent generations of the
        same requested_id can't actually happen. But the guard makes
        the contract explicit and survives any future change that
        releases the lock during LLM calls.

        Raises LLMUnavailable if the LLM is unreachable — the caller
        (move command) should refuse the move with a "path is shrouded"
        message rather than create a permanent stub-room that pollutes
        the map. For other failures (malformed JSON, etc.) we fall
        back to a stub after retries — that's a one-off content
        glitch, not a temporary infra outage."""
        new_id = requested_id or _allocate_room_id(source.zone_tag)

        # Fast-path: another writer already created this room.
        if world_store.room_exists(world_id, new_id):
            return world_store.load_room(world_id, new_id)

        last_err: Exception | None = None
        for _attempt in range(max_retries + 1):
            try:
                payload = self._call_room_gen(source, direction, new_id)
                # Re-check post-LLM: if a concurrent writer landed
                # while our LLM was thinking, drop our payload and
                # adopt theirs. Avoids two players overwriting each
                # other's room when both reach the same exit.
                if world_store.room_exists(world_id, new_id):
                    return world_store.load_room(world_id, new_id)
                return self._materialize_room(source, direction, new_id, payload, world_id)
            except LLMUnavailable:
                # Don't retry — the LLM is OFF, not flaky. Bubble up.
                raise
            except Exception as e:
                last_err = e
                continue
        return self._stub_room(source, direction, new_id, world_id,
                               str(last_err) if last_err else "unknown")

    def _call_room_gen(self, source: Room, direction: str, new_id: str) -> dict:
        raw = self.llm(ROOM_GEN_PERSONA, _build_room_gen_prompt(source, direction))
        return _extract_json(raw)

    def _materialize_room(self, source: Room, direction: str, new_id: str,
                          payload: dict, world_id: str) -> Room:
        name = str(payload.get("name", "Uncharted Place")).strip() or "Uncharted Place"
        desc = str(payload.get("description", "")).strip() or "An unremarkable place."
        zone_tag = str(payload.get("zone_tag", "") or source.zone_tag or "wild")

        back_dir = opposite(direction) or direction
        exits: dict[str, str] = {back_dir: source.id}
        forward_dirs = payload.get("exits") or []
        if isinstance(forward_dirs, dict):
            forward_dirs = list(forward_dirs.keys())
        for d in forward_dirs:
            d = str(d).lower().strip()
            if d in (back_dir, direction) or d in exits:
                continue
            if d not in VALID_DIRS:
                continue
            exits[d] = _allocate_room_id(zone_tag)

        # Guardrail: every generated room must have at least 1 forward exit
        # so the world keeps growing. The DM persona requires this; if the
        # LLM ignores the rule we add `direction` as a fallback (continue
        # straight ahead).
        if len(exits) == 1:  # only the back-edge so far
            exits[direction] = _allocate_room_id(zone_tag)

        npcs = []
        for n in (payload.get("npcs") or []):
            try:
                npcs.append(NPC(
                    npc_id=str(n.get("npc_id") or f"npc_{uuid.uuid4().hex[:8]}"),
                    name=str(n["name"]),
                    title=str(n.get("title", "")),
                    personality=str(n.get("personality", "")),
                    faction=str(n.get("faction", "none")),
                    routines=list(n.get("routines") or [
                        {"start_hr": 0, "end_hr": 24, "location_id": new_id, "activity": "going about their business"},
                    ]),
                    lore=[str(f) for f in (n.get("lore") or []) if isinstance(f, str)],
                    wares=list(n.get("wares") or []),
                ))
            except (KeyError, TypeError):
                continue

        room = Room(id=new_id, name=name, description=desc, exits=exits,
                    zone_tag=zone_tag, npcs=npcs)
        world_store.save_room(world_id, room)
        world_store.add_edge(world_id, source.id, direction, new_id)
        for d, dest in exits.items():
            if d == back_dir:
                continue
            world_store.add_edge(world_id, new_id, d, dest, bidirectional=False)

        for m_data in (payload.get("mobs") or []):
            mob = self._build_mob(m_data, new_id, zone_tag)
            if mob is not None:
                world_store.add_mob(world_id, mob)
        for it_data in (payload.get("items") or []):
            item, item_id = self._build_item(it_data)
            if item is not None:
                world_store.add_item(world_id, item_id, item, f"room:{new_id}")
        return room

    def _stub_room(self, source: Room, direction: str, new_id: str, world_id: str,
                   error: str) -> Room:
        back_dir = opposite(direction) or direction
        room = Room(
            id=new_id,
            name="Misty Crossing",
            description=("The path winds into a grey haze. Nothing is clear here — "
                         "perhaps the wind is to blame. (Generation fallback)"),
            exits={back_dir: source.id},
            zone_tag=source.zone_tag or "wild",
        )
        world_store.save_room(world_id, room)
        world_store.add_edge(world_id, source.id, direction, new_id)
        return room

    def _build_mob(self, data: dict, room_id: str, zone_tag: str) -> Mob | None:
        try:
            stats = data.get("stats") or {"STR": 10, "DEX": 10, "CON": 10, "INT": 6, "WIS": 8, "CHA": 6}
            mob_id = str(data.get("mob_id") or f"mob_{uuid.uuid4().hex[:10]}")
            return Mob(
                name=str(data["name"]),
                kind=str(data.get("kind", data.get("name", "creature")).lower().replace(" ", "_")),
                hp=int(data.get("hp", 10)),
                max_hp=int(data.get("hp", 10)),
                atk=int(data.get("atk", 2)),
                ac=int(data.get("ac", 11)),
                level=int(data.get("level", 1)),
                stats={k.upper(): int(v) for k, v in stats.items()},
                damage_die=str(data.get("damage_die", "1d4")),
                damage_bonus=int(data.get("damage_bonus", 0)),
                abilities=list(data.get("abilities") or ["attack"]),
                personality=str(data.get("personality", "")),
                faction=str(data.get("faction", "wild_beast")),
                aggression=int(data.get("aggression", 5)),
                xp_value=int(data.get("xp_value", 25)),
                home_room=room_id,
                current_room=room_id,
                wander_radius=int(data.get("wander_radius", 2)),
                zone_tag=zone_tag,
                mob_id=mob_id,
            )
        except (KeyError, ValueError, TypeError):
            return None

    def _build_item(self, data: dict) -> tuple[Item | None, str]:
        try:
            item_id = str(data.get("item_id") or f"item_{uuid.uuid4().hex[:10]}")
            item = Item(
                name=str(data["name"]),
                slot=str(data.get("slot", "consumable")),
                damage_die=str(data.get("damage_die", "")),
                damage_type=str(data.get("damage_type", "slashing")),
                armor_base=int(data.get("armor_base", 0)),
                allowed_classes=list(data.get("allowed_classes") or []) or None,
            )
            return item, item_id
        except (KeyError, ValueError, TypeError):
            return None, ""
