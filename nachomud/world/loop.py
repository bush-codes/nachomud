"""WorldLoop: the single owner of the shared world.

Every actor's command flows through one threading.Lock, processed
serially against the shared world. A background tick task runs
`tick_mobs_for_rooms` on a wall-clock cadence and pushes witness lines
onto the affected actors' Game queues. Both ends share the same lock
so commands and ticks never interleave.

Sync callers (Session/Game pipeline driven via `loop.run_in_executor`)
acquire the lock directly; the async tick task acquires it via
`asyncio.to_thread`.

The 4 built-in agents are auto-registered on first start; their AgentState
saves are minted in `data/players/agent_<id>.json` if not already
present. Human players register their own actor when they enter the
game (the WS handler plumbs this through Session._enter_in_game).
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
import threading
from collections import deque
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any, Optional

import nachomud.characters.save as player_mod
import nachomud.world.starter as starter
import nachomud.world.store as world_store
import nachomud.world.transcript_log as transcript_log
from nachomud.ai.agents import AGENT_DEFINITIONS, build_agent_state
from nachomud.ai.dm import DM, LLMFn
from nachomud.ai.npc import NPCDialogue
from nachomud.engine.game import Game
from nachomud.models import AgentState
from nachomud.world.mobs import tick_mobs_for_rooms, witness_lines


log = logging.getLogger("nachomud.worldloop")


# How often the world advances by one game-minute of mob movement.
GLOBAL_TICK_SECONDS = 6.0
MINUTES_PER_TICK = 1
TRANSCRIPT_LIMIT = 200


@dataclass
class Subscriber:
    """One viewer connection. Holds an asyncio.Queue the WorldLoop pushes
    messages onto from sync code (via call_soon_threadsafe). The WS
    handler's forwarder task drains the queue and writes to the socket.

    `actor_id` is the actor this subscriber currently watches; empty
    string means "pre-actor" (welcome / char_create flow).

    `self_transcript` holds the most-recent pre-actor messages this WS
    received. When the user clicks back to My Player before they've
    created a character, the server replays this so the welcome flow
    reappears in the freshly-cleared pane."""
    queue: asyncio.Queue
    actor_id: str = ""
    self_transcript: deque = field(default_factory=lambda: deque(maxlen=TRANSCRIPT_LIMIT))


@dataclass
class Actor:
    """One participant in the shared world: human or AI agent.

    `kind` is "human" or "agent". `agent_def` is set only for AI actors
    and points to the entry in AGENT_DEFINITIONS that drives them."""
    actor_id: str
    kind: str               # "human" | "agent"
    state: AgentState
    game: Any               # Game instance — typed Any to avoid circular import
    transcript: deque = field(default_factory=lambda: deque(maxlen=TRANSCRIPT_LIMIT))
    agent_def: dict | None = None

    def record(self, msgs: Iterable) -> None:
        """Append messages to the per-actor transcript ring buffer
        AND the persistent disk log. Subscribers backfill from disk
        (24h window) when they switch views — the in-memory ring is
        only retained as a fast path for very-recent reads."""
        for m in msgs:
            self.transcript.append(m)
            transcript_log.append(self.actor_id, m)


@dataclass
class WorldLoop:
    world_id: str = "default"
    spawn_room: str = "silverbrook.inn"
    dm_llm: LLMFn | None = None
    npc_llm: LLMFn | None = None
    npc_summarizer: LLMFn | None = None

    actors: dict[str, Actor] = field(default_factory=dict)
    subscribers: list[Subscriber] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _tick_task: Optional[asyncio.Task] = None
    _agent_tasks: list[asyncio.Task] = field(default_factory=list)
    _stopped: bool = False
    _booted: bool = False
    _event_loop: Optional[asyncio.AbstractEventLoop] = None
    enable_agent_runner: bool = True

    # ── Lifecycle ──

    async def start(self) -> None:
        if self._booted:
            return
        self._booted = True
        self._event_loop = asyncio.get_event_loop()
        await asyncio.to_thread(starter.seed_world, self.world_id, "silverbrook")
        await asyncio.to_thread(self._mint_agent_actors)
        self._tick_task = asyncio.create_task(self._tick_loop(), name="worldloop.tick")
        if self.enable_agent_runner:
            self._spawn_agent_runners()
        log.info("WorldLoop started — world=%s, %d actors registered",
                 self.world_id, len(self.actors))

    async def stop(self) -> None:
        self._stopped = True
        for t in self._agent_tasks:
            t.cancel()
        for t in self._agent_tasks:
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await t
        self._agent_tasks = []
        if self._tick_task is not None:
            self._tick_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._tick_task
            self._tick_task = None
        with self._lock:
            for actor in self.actors.values():
                try:
                    player_mod.save_player(actor.state)
                except Exception:
                    log.exception("save_player failed at shutdown for %s", actor.actor_id)

    def _spawn_agent_runners(self) -> None:
        from nachomud.ai.runner import AGENT_TICK_SECONDS, _default_llm, agent_loop
        agents = [a for a in self.actors.values() if a.kind == "agent"]
        if not agents:
            return
        stagger_step = AGENT_TICK_SECONDS / max(1, len(agents))
        for i, actor in enumerate(agents):
            task = asyncio.create_task(
                agent_loop(self, actor, llm_fn=_default_llm,
                           stagger_seconds=i * stagger_step),
                name=f"agent_runner.{actor.actor_id}",
            )
            self._agent_tasks.append(task)

    # ── Registry ──

    def _mint_agent_actors(self) -> None:
        for definition in AGENT_DEFINITIONS:
            actor_id = definition["actor_id"]
            if player_mod.player_exists(actor_id):
                state = player_mod.load_player(actor_id)
                # Rescue: if the saved room no longer exists in the world,
                # bounce them back to spawn rather than crash on load_room.
                if state.room_id and not world_store.room_exists(self.world_id, state.room_id):
                    log.info("rescuing %s from missing room %s -> %s",
                             actor_id, state.room_id, self.spawn_room)
                    state.room_id = self.spawn_room
                    player_mod.save_player(state)
            else:
                state = build_agent_state(definition, world_id=self.world_id,
                                          spawn_room=self.spawn_room)
                player_mod.save_player(state)
            actor = self._build_actor(actor_id, "agent", state, definition)
            self.actors[actor_id] = actor

    def _build_actor(self, actor_id: str, kind: str, state: AgentState,
                     definition: dict | None) -> Actor:
        game = Game(
            player=state,
            dm=DM(llm=self.dm_llm),
            npc_dialogue=NPCDialogue(llm=self.npc_llm, summarizer=self.npc_summarizer),
            co_residents_fn=lambda room_id, _aid=actor_id: self._co_residents(_aid, room_id),
        )
        return Actor(actor_id=actor_id, kind=kind, state=state, game=game,
                     agent_def=definition)

    def _co_residents(self, exclude_actor_id: str, room_id: str) -> list[str]:
        """Display names of other actors currently in `room_id`. Called
        by Game.render_room. Read-only over self.actors — caller already
        holds _lock (via submit_command / start_actor)."""
        out: list[str] = []
        for aid, a in self.actors.items():
            if aid == exclude_actor_id:
                continue
            if a.state.room_id != room_id:
                continue
            display = (a.agent_def or {}).get("display_name") or a.state.name or aid
            out.append(display)
        return out

    def register_human(self, state: AgentState) -> Actor:
        """Register a human actor when they finish welcome / char-create.
        Reconnect-safe: rebinds the existing actor if there's already one
        for this player_id."""
        actor_id = f"human_{state.player_id}"
        new = False
        with self._lock:
            existing = self.actors.get(actor_id)
            if existing is not None:
                existing.state = state
                existing.game = Game(
                    player=state,
                    dm=DM(llm=self.dm_llm),
                    npc_dialogue=NPCDialogue(llm=self.npc_llm,
                                             summarizer=self.npc_summarizer),
                    co_residents_fn=lambda room_id, _aid=actor_id: self._co_residents(_aid, room_id),
                )
                actor = existing
            else:
                actor = self._build_actor(actor_id, "human", state, None)
                self.actors[actor_id] = actor
                new = True
        if new:
            self.broadcast_actor_list()
        return actor

    def unregister_human(self, actor_id: str) -> None:
        with self._lock:
            actor = self.actors.pop(actor_id, None)
        if actor is None:
            return
        try:
            player_mod.save_player(actor.state)
        except Exception:
            log.exception("save_player failed for %s", actor_id)
        for sub in self.subscribers:
            if sub.actor_id == actor_id:
                sub.actor_id = ""
        self.broadcast_actor_list()

    def get_actor(self, actor_id: str) -> Optional[Actor]:
        return self.actors.get(actor_id)

    def list_actors(self) -> list[dict]:
        out = []
        for a in self.actors.values():
            display = (a.agent_def or {}).get("display_name", a.state.name)
            out.append({
                "actor_id": a.actor_id,
                "kind": a.kind,
                "display_name": display,
                "name": a.state.name,
                "race": a.state.race,
                "class": a.state.agent_class,
                "level": a.state.level,
                "hp": a.state.hp,
                "max_hp": a.state.max_hp,
                "alive": a.state.alive,
                "room_id": a.state.room_id,
            })
        return out

    # ── Subscribers ──

    def add_subscriber(self, queue: asyncio.Queue) -> Subscriber:
        sub = Subscriber(queue=queue, actor_id="")
        self.subscribers.append(sub)
        return sub

    def remove_subscriber(self, sub: Subscriber) -> None:
        with contextlib.suppress(ValueError):
            self.subscribers.remove(sub)

    def set_subscription(self, sub: Subscriber, actor_id: str) -> bool:
        """Switch which actor `sub` watches. The subscribed event goes
        out FIRST so the client clears its pane and updates activeActorId
        before transcript replay arrives. Empty actor_id → replay the
        subscriber's pre-actor self_transcript (welcome flow)."""
        if actor_id and actor_id not in self.actors:
            return False
        sub.actor_id = actor_id
        self._enqueue(sub.queue, ("event",
                                  {"type": "subscribed", "actor_id": actor_id}))
        if actor_id:
            # Replay from the persistent disk log so spectators get
            # 24h of history, not just whatever's accumulated since
            # the container last started. Falls back to the in-memory
            # ring if the log is unreadable.
            history = transcript_log.read_recent(actor_id)
            if not history:
                actor = self.actors[actor_id]
                history = list(actor.transcript)
            for item in history:
                self._enqueue(sub.queue, ("scoped", actor_id, item))
        else:
            for item in list(sub.self_transcript):
                self._enqueue(sub.queue, ("self", item))
        return True

    def _broadcast(self, actor_id: str, msgs: list) -> None:
        if not msgs:
            return
        targets = [s for s in self.subscribers if s.actor_id == actor_id]
        if not targets:
            return
        for sub in targets:
            for m in msgs:
                self._enqueue(sub.queue, ("scoped", actor_id, m))

    def _enqueue(self, queue: asyncio.Queue, item) -> None:
        loop = self._event_loop
        if loop is None or loop.is_closed():
            return
        with contextlib.suppress(RuntimeError):
            loop.call_soon_threadsafe(queue.put_nowait, item)

    def actor_list_event(self) -> dict:
        return {"type": "actor_list", "actors": self.list_actors()}

    def broadcast_actor_list(self) -> None:
        evt = self.actor_list_event()
        for sub in list(self.subscribers):
            self._enqueue(sub.queue, ("event", evt))

    # ── Command processing ──

    def submit_command(self, actor_id: str, text: str, *,
                       echo: bool = False) -> list:
        """Run a single command for the named actor under the world lock.
        Returns the messages produced and broadcasts them to subscribers.
        Cross-actor witnesses are queued onto bystanders if the mover
        changed rooms.

        `echo`: prepend a "> {text}" line so spectators see what an agent
        decided. Humans don't need this — they see their own keystrokes
        locally in xterm."""
        actor = self.actors.get(actor_id)
        if actor is None:
            log.warning("submit_command for unknown actor %s", actor_id)
            return []
        echo_msg = None
        if echo and text:
            echo_msg = ("output", f"\x1b[2;36m> {text}\x1b[0m\r\n")
        with self._lock:
            if echo_msg is not None:
                actor.record([echo_msg])
            old_room = actor.state.room_id
            try:
                msgs = actor.game.handle(text)
            except Exception:
                log.exception("game.handle failed for %s", actor_id)
                if echo_msg is not None:
                    self._broadcast(actor_id, [echo_msg])
                return []
            new_room = actor.state.room_id
            if new_room != old_room:
                self._cross_actor_witness(actor, old_room, new_room)
            actor.record(msgs)
            self._sync_visited(actor)
        if echo_msg is not None:
            self._broadcast(actor_id, [echo_msg])
        self._broadcast(actor_id, msgs)
        return msgs

    def start_actor(self, actor_id: str) -> list:
        actor = self.actors.get(actor_id)
        if actor is None:
            return []
        with self._lock:
            try:
                msgs = actor.game.start()
            except Exception:
                log.exception("game.start failed for %s", actor_id)
                return []
            actor.record(msgs)
            self._sync_visited(actor)
        self._broadcast(actor_id, msgs)
        return msgs

    @staticmethod
    def _sync_visited(actor: Actor) -> None:
        rid = actor.state.room_id
        if rid and rid not in actor.state.visited_rooms:
            actor.state.visited_rooms.append(rid)

    def _cross_actor_witness(self, mover: Actor, old_room: str, new_room: str) -> None:
        """When `mover` changed rooms, queue 'X heads east' / 'X arrives
        from the south' onto every other actor in old/new room."""
        if not old_room and not new_room:
            return
        name = mover.state.name or mover.actor_id
        direction_left = ""
        if old_room and new_room:
            try:
                graph = world_store.load_graph(self.world_id)
                for d, dest in graph.get(old_room, {}).items():
                    if dest == new_room:
                        direction_left = d
                        break
            except Exception:
                pass
        direction_arrived = (world_store.opposite_direction(direction_left)
                             if direction_left else "")
        for other in self.actors.values():
            if other.actor_id == mover.actor_id:
                continue
            if old_room and other.state.room_id == old_room:
                line = (f"{name} heads {direction_left}." if direction_left
                        else f"{name} departs.")
                other.game.queue_witness([line])
            elif new_room and other.state.room_id == new_room:
                line = (f"{name} arrives from the {direction_arrived}."
                        if direction_arrived else f"{name} appears.")
                other.game.queue_witness([line])

    # ── Global tick ──

    async def _tick_loop(self) -> None:
        while not self._stopped:
            try:
                await asyncio.sleep(GLOBAL_TICK_SECONDS)
                await asyncio.to_thread(self._global_tick_locked)
            except asyncio.CancelledError:
                return
            except Exception:
                log.exception("global tick failed")
                await asyncio.sleep(GLOBAL_TICK_SECONDS)

    def _global_tick_locked(self) -> None:
        with self._lock:
            self._global_tick()

    def _global_tick(self) -> None:
        if not self.actors:
            return
        active_rooms: set[str] = {
            a.state.room_id for a in self.actors.values()
            if a.state.alive and a.state.room_id
        }
        if not active_rooms:
            return
        witness_by_room = tick_mobs_for_rooms(self.world_id, active_rooms,
                                              minutes=MINUTES_PER_TICK)
        if not witness_by_room:
            return
        for actor in self.actors.values():
            w = witness_by_room.get(actor.state.room_id)
            if not w or not w.has_any:
                continue
            actor.game.queue_witness(witness_lines(w))


# ── Module-level singleton ──

_singleton: Optional[WorldLoop] = None


def get_world_loop() -> Optional[WorldLoop]:
    return _singleton


def set_world_loop(loop: WorldLoop) -> None:
    global _singleton
    _singleton = loop
