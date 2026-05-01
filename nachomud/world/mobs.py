"""Mob mobility AI: idle / wander / pursue / return state machine.

Rule-based, no LLM calls. Cheap, predictable, persists every move so the
world-state on disk is always coherent. Witness messages are emitted when a
mob enters or leaves the player's current room.

Called per game-minute by game.py after the clock advances. The "hot tick"
covers mobs in or adjacent to the player's room (those whose movement the
player can perceive); the "cold tick" applies to distant mobs at low
probability so they make slow progress without dominating CPU.
"""
from __future__ import annotations

from dataclasses import dataclass

import nachomud.world.store as world_store
from nachomud.rules.dice import random_chance, random_choice
from nachomud.models import Mob
from nachomud.world.directions import opposite as _opposite

# ── Probabilities (per game-minute) ──
P_IDLE_TO_WANDER = 0.05
P_WANDER_STEP = 0.40       # if wandering, chance to step this minute
P_WANDER_END = 0.30        # after step or 3 hops, chance to revert to idle
P_RETURN_STEP = 0.50
P_PURSUE_STEP = 0.80
P_DISTANT_TICK = 0.10      # cold-tick probability for far mobs


# ── Witness emit ──

@dataclass
class Witness:
    """Witness messages for mob transitions in/out of the player's room."""
    entered: list[tuple[str, str]] = None  # (mob_name, from_dir)
    left: list[tuple[str, str]] = None     # (mob_name, to_dir)

    def __post_init__(self):
        if self.entered is None:
            self.entered = []
        if self.left is None:
            self.left = []

    @property
    def has_any(self) -> bool:
        return bool(self.entered or self.left)


# ── Movement primitives ──

def _adjacent(graph: dict, room_id: str) -> dict[str, str]:
    return graph.get(room_id, {})


def _bfs_step_toward(graph: dict, start: str, target: str, max_depth: int = 10) -> str:
    """Return the direction to take from `start` to make progress toward `target`."""
    if start == target:
        return ""
    seen = {start}
    queue = [(start, [])]
    while queue:
        node, path = queue.pop(0)
        if len(path) > max_depth:
            return ""
        for d, nxt in _adjacent(graph, node).items():
            if nxt == target:
                return path[0] if path else d
            if nxt in seen:
                continue
            seen.add(nxt)
            queue.append((nxt, [*path, d]))
    return ""


def _hops_from_home(graph: dict, current: str, home: str, max_depth: int = 10) -> int:
    if current == home:
        return 0
    seen = {current}
    queue = [(current, 0)]
    while queue:
        node, depth = queue.pop(0)
        if depth > max_depth:
            return max_depth + 1
        for nxt in _adjacent(graph, node).values():
            if nxt == home:
                return depth + 1
            if nxt in seen:
                continue
            seen.add(nxt)
            queue.append((nxt, depth + 1))
    return max_depth + 1


def _zone_filtered_exits(world_id: str, room_id: str, zone_tag: str, graph: dict) -> dict[str, str]:
    """Return exits that lead to rooms in the same zone (and that exist on disk)."""
    out = {}
    for d, dest in _adjacent(graph, room_id).items():
        if not world_store.room_exists(world_id, dest):
            continue
        try:
            r = world_store.load_room(world_id, dest)
        except FileNotFoundError:
            continue
        if zone_tag and r.zone_tag and r.zone_tag != zone_tag:
            continue
        out[d] = dest
    return out


# ── Per-mob tick ──

def _move_mob(mob: Mob, direction: str, dest: str,
              witnesses: dict[str, Witness], active_rooms: set[str]) -> None:
    """Apply a movement: update mob.current_room and emit witness messages
    for any active room the mob crossed in or out of."""
    name = mob.name or mob.kind or "Something"
    src = mob.current_room
    if src in active_rooms and src != dest:
        witnesses.setdefault(src, Witness()).left.append((name, direction))
    if dest in active_rooms and dest != src:
        witnesses.setdefault(dest, Witness()).entered.append(
            (name, _opposite(direction) or direction))
    mob.current_room = dest


def _tick_one_mob(mob: Mob, world_id: str, graph: dict,
                  pursue_target: str, witnesses: dict[str, Witness],
                  active_rooms: set[str], hot: bool) -> bool:
    """Tick one mob's AI. Returns True if state was modified (caller persists)."""
    if not mob.alive:
        return False

    # Cold tick: low probability
    if not hot and not random_chance(P_DISTANT_TICK):
        return False

    state = mob.ai_state or "idle"

    if state == "pursue":
        if random_chance(P_PURSUE_STEP):
            exits = _zone_filtered_exits(world_id, mob.current_room, mob.zone_tag, graph)
            if not exits:
                mob.ai_state = "return"
                return True
            target_dir = mob.ai_target if mob.ai_target in exits else None
            if not target_dir and pursue_target:
                target_dir = _bfs_step_toward(graph, mob.current_room, pursue_target)
            if target_dir and target_dir in exits:
                _move_mob(mob, target_dir, exits[target_dir], witnesses, active_rooms)
            else:
                mob.ai_state = "return"
            return True
        return False

    if state == "return":
        if random_chance(P_RETURN_STEP):
            if mob.current_room == mob.home_room:
                mob.ai_state = "idle"
                return True
            exits = _zone_filtered_exits(world_id, mob.current_room, mob.zone_tag, graph)
            if not exits:
                mob.ai_state = "idle"
                return True
            d = _bfs_step_toward(graph, mob.current_room, mob.home_room)
            if d and d in exits:
                _move_mob(mob, d, exits[d], witnesses, active_rooms)
            else:
                mob.ai_state = "idle"
            return True
        return False

    if state == "wander":
        hops = _hops_from_home(graph, mob.current_room, mob.home_room, max_depth=mob.wander_radius + 2)
        if hops >= max(1, mob.wander_radius):
            mob.ai_state = "return"
            return True
        if random_chance(P_WANDER_STEP):
            exits = _zone_filtered_exits(world_id, mob.current_room, mob.zone_tag, graph)
            if exits:
                direction = random_choice(list(exits.keys()))
                _move_mob(mob, direction, exits[direction], witnesses, active_rooms)
                if random_chance(P_WANDER_END):
                    mob.ai_state = "idle"
                return True
        return False

    # idle
    if random_chance(P_IDLE_TO_WANDER):
        mob.ai_state = "wander"
        return True
    return False


# ── Public API ──

def tick_mobs_for_rooms(world_id: str, active_rooms: set[str],
                        minutes: int = 1) -> dict[str, Witness]:
    """Multi-actor variant: returns witness events keyed by room. Mobs in
    or adjacent to any active room get the "hot" tick; distant mobs use
    the cold-tick probability. Witnesses are emitted only for active
    rooms (the WorldLoop distributes them to actors standing there)."""
    witnesses: dict[str, Witness] = {}
    if minutes <= 0:
        return witnesses

    graph = world_store.load_graph(world_id)
    mobs = world_store.load_mobs(world_id)
    if not mobs:
        return witnesses

    hot_room_ids: set[str] = set(active_rooms)
    for room_id in list(active_rooms):
        for dest in _adjacent(graph, room_id).values():
            hot_room_ids.add(dest)

    # Pursue logic needs *some* target. Pick any active room.
    pursue_target = next(iter(active_rooms), "") if active_rooms else ""

    for _ in range(minutes):
        changed_ids = []
        for mob_id, mob in list(mobs.items()):
            hot = mob.current_room in hot_room_ids
            if _tick_one_mob(mob, world_id, graph, pursue_target,
                              witnesses, active_rooms, hot=hot):
                changed_ids.append(mob_id)
        if changed_ids:
            world_store.save_mobs(world_id, mobs)

    return witnesses


def tick_mobs(world_id: str, player_room: str, minutes: int = 1) -> Witness:
    """Single-actor wrapper around tick_mobs_for_rooms — preserved so the
    existing single-player path and tests keep working unchanged."""
    by_room = tick_mobs_for_rooms(world_id, {player_room}, minutes)
    return by_room.get(player_room, Witness())


def witness_lines(witness: Witness) -> list[str]:
    """Render witness as a list of human-readable strings for the event log."""
    out = []
    for name, from_dir in witness.entered:
        if from_dir:
            out.append(f"{name} arrives from the {from_dir}.")
        else:
            out.append(f"{name} appears.")
    for name, to_dir in witness.left:
        if to_dir:
            out.append(f"{name} heads {to_dir}.")
        else:
            out.append(f"{name} departs.")
    return out
