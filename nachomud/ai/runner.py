"""AI agent runner — one async task per built-in agent.

The runner builds a sensory snapshot, asks the LLM (with the agent's
personality system prompt) for a single command, then submits it through
the WorldLoop's command lock. LLM calls happen *outside* the lock so a
slow LLM doesn't block other actors; the world serializes only the brief
state-read and command-dispatch steps.
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable

import nachomud.ai.llm as llm
import nachomud.settings as config
import nachomud.world.store as world_store
from nachomud.models import AgentState, Room
from nachomud.world.loop import Actor
from nachomud.world.routines import hour_from_minute, npcs_in_room


log = logging.getLogger("nachomud.agentrunner")


from nachomud.settings import AGENT_LLM_TIMEOUT_SECONDS, AGENT_TICK_SECONDS  # noqa: E402
DEAD_TICK_SECONDS = 4.0


LLMFn = Callable[[str, str], str]


def _default_llm(system: str, user: str) -> str:
    return llm.chat(system=system, message=user, model=config.LLM_FAST_MODEL,
                    max_tokens=80)


def _snapshot(actor: Actor) -> dict:
    """Read-only snapshot of the actor's view of the world."""
    state = actor.state
    in_combat = (actor.game._encounter is not None
                 and actor.game._encounter.is_active())
    try:
        room = world_store.load_room(state.world_id, state.room_id)
    except Exception:
        room = None
    return {"state": state, "room": room, "in_combat": in_combat}


def build_user_prompt(snap: dict) -> str:
    if snap["in_combat"]:
        return _build_combat_prompt(snap)
    return _build_explore_prompt(snap)


def _identity_lines(state: AgentState) -> list[str]:
    bar = f"HP {state.hp}/{state.max_hp}"
    if state.max_mp:
        bar += f"  MP {state.mp}/{state.max_mp}"
    if state.max_ap:
        bar += f"  AP {state.ap}/{state.max_ap}"
    return [
        f"You are {state.name} the {state.race} {state.agent_class} (L{state.level}).",
        bar,
    ]


def _build_combat_prompt(snap: dict) -> str:
    """Combat-specific prompt. Strips exits/items/NPCs/description (none
    advance the turn) and lists the agent's actual ability names so the
    LLM doesn't have to guess from an abstract `<ability>` placeholder."""
    state: AgentState = snap["state"]
    room: Room | None = snap["room"]
    parts: list[str] = _identity_lines(state)

    if room is not None:
        mobs = world_store.mobs_in_room(state.world_id, room.id, alive_only=True)
        if mobs:
            parts.append("")
            parts.append("Enemies in combat with you:")
            parts.extend(f"  - {m.name} (HP {m.hp}/{m.max_hp})" for m in mobs)

    parts.append("")
    parts.append("⚔ YOU ARE IN COMBAT — your turn ⚔")
    parts.append("Movement, look, get, talk, dm — none of these advance the turn.")
    abilities = list(state.abilities or [])
    if "attack" not in abilities:
        abilities.insert(0, "attack")
    parts.append("Combat commands available: " + ", ".join(abilities) + ", flee.")
    parts.append("Most take a target: `<command> <enemy name>` "
                 "(e.g. `attack Wild Boar`, `smite Wild Boar`). "
                 "Mix it up — abilities are usually more interesting than plain attack.")
    parts.append("Reply with ONE line: just the command. No commentary, no quotes.")
    return "\n".join(parts)


def _build_explore_prompt(snap: dict) -> str:
    state: AgentState = snap["state"]
    room: Room | None = snap["room"]

    parts: list[str] = _identity_lines(state)
    if state.abilities:
        parts.append(f"Abilities: {', '.join(state.abilities)}")

    if room is not None:
        parts.append("")
        parts.append(f"=== {room.name} ===")
        parts.append(room.description)
        hour = hour_from_minute(state.game_clock.get("minute", 480))
        npc_pairs = npcs_in_room(room.npcs, room.id, hour)
        if npc_pairs:
            parts.append("People here: "
                         + ", ".join(f"{n.name} ({n.title})" for n, _ in npc_pairs))
        mobs = world_store.mobs_in_room(state.world_id, room.id, alive_only=True)
        if mobs:
            parts.append("Hostiles: "
                         + ", ".join(f"{m.name} (HP {m.hp}/{m.max_hp})" for m in mobs))
        items = world_store.items_in_room(state.world_id, room.id)
        if items:
            parts.append("Ground: " + ", ".join(i.get("name", "?") for i in items))
        if room.exits:
            parts.append("Exits: " + ", ".join(sorted(room.exits.keys())))
    else:
        parts.append("(You can't read the room.)")

    if state.action_history:
        parts.append("")
        parts.append("Your recent actions: "
                     + " | ".join(state.action_history[-5:]))

    parts.append("")
    parts.append("Pick exactly one command. Movement: n/s/e/w/up/down. "
                 "`look`, `map`, `talk <npc>`, `dm <message>`, `attack <mob>`, "
                 "`get <item>`, `wait`. Free-form actions also work — they go "
                 "to the Dungeon Master for adjudication.")
    parts.append("Reply with ONE line: just the command. No commentary, no quotes.")
    return "\n".join(parts)


def parse_command(reply: str) -> str:
    """Strip the LLM reply down to a single command line. Fallback to
    `look` for empty / unparseable output so the world keeps moving."""
    if not reply:
        return "look"
    for raw in reply.splitlines():
        line = raw.strip().strip("`").strip("\"'").strip()
        for prefix in ("COMMAND:", "command:", "> ", ">", "Action:", "action:"):
            if line.startswith(prefix):
                line = line[len(prefix):].strip()
        if line:
            return line[:200]
    return "look"


async def agent_loop(world_loop, actor: Actor, *, llm_fn: LLMFn,
                     tick_seconds: float = AGENT_TICK_SECONDS,
                     stagger_seconds: float = 0.0,
                     stop_event: asyncio.Event | None = None) -> None:
    """Drive one agent forever. Cancelled by WorldLoop.stop()."""
    if stagger_seconds > 0:
        try:
            await asyncio.sleep(stagger_seconds)
        except asyncio.CancelledError:
            return

    started = False
    while True:
        if stop_event is not None and stop_event.is_set():
            return
        try:
            if not started:
                await asyncio.to_thread(world_loop.start_actor, actor.actor_id)
                started = True
            if not actor.state.alive:
                await asyncio.sleep(DEAD_TICK_SECONDS)
                continue
            await _tick_once(world_loop, actor, llm_fn)
        except asyncio.CancelledError:
            return
        except Exception:
            log.exception("agent loop tick failed for %s", actor.actor_id)
        try:
            await asyncio.sleep(tick_seconds)
        except asyncio.CancelledError:
            return


async def _tick_once(world_loop, actor: Actor, llm_fn: LLMFn) -> None:
    def _snapshot_locked():
        with world_loop._lock:
            snap = _snapshot(actor)
            return snap, build_user_prompt(snap)

    snap, user_prompt = await asyncio.to_thread(_snapshot_locked)
    system_prompt = (actor.agent_def or {}).get("system_prompt", "")

    try:
        reply = await asyncio.wait_for(
            asyncio.to_thread(llm_fn, system_prompt, user_prompt),
            timeout=AGENT_LLM_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        # The worker thread keeps running until llm_fn returns; we just
        # stop waiting on it so the agent loop can tick again. Skipping
        # the command is preferable to parking the loop forever.
        log.warning("LLM call timed out after %.0fs for %s — skipping tick",
                    AGENT_LLM_TIMEOUT_SECONDS, actor.actor_id)
        return
    except Exception:
        log.exception("LLM call failed for %s — skipping tick", actor.actor_id)
        return
    command = parse_command(reply)
    if snap.get("in_combat"):
        command = _coerce_combat_command(command, actor, snap)
    log.info("agent %s -> %s", actor.actor_id, command)
    await asyncio.to_thread(_submit_with_echo, world_loop, actor.actor_id, command)


def _coerce_combat_command(command: str, actor: Actor, snap: dict) -> str:
    """If the LLM picked a non-combat verb while in combat, substitute
    `attack <first hostile>` so the turn at least advances. Without
    this, an invalid combat command just sits and combat stalls
    indefinitely (handle_player_input rejects it without progressing
    the round)."""
    first = command.split()[0].lower() if command else ""
    valid = {"attack", "defend", "flee", "look", "status", "help"}
    valid.update(a.lower() for a in (actor.state.abilities or []))
    if first in valid:
        return command
    room = snap.get("room")
    if room is not None:
        mobs = world_store.mobs_in_room(actor.state.world_id, room.id, alive_only=True)
        if mobs:
            return f"attack {mobs[0].name}"
    return "flee"


def _submit_with_echo(world_loop, actor_id: str, command: str) -> None:
    world_loop.submit_command(actor_id, command, echo=True)
