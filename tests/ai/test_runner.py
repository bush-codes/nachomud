"""Tests for ai/runner.py — focused on failure modes that have caused
silent prod stalls. Currently: a hung LLM must not park the agent loop."""
from __future__ import annotations

import asyncio
import threading
import time
from types import SimpleNamespace

import nachomud.ai.runner as runner


class _FakeLoop:
    """Minimum surface _tick_once touches: a lock and submit_command."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.submitted: list[tuple[str, str]] = []

    def submit_command(self, actor_id: str, command: str, *, echo: bool = False) -> None:
        self.submitted.append((actor_id, command))


def _fake_actor() -> SimpleNamespace:
    return SimpleNamespace(actor_id="agent_test", agent_def={"system_prompt": "be brief"})


def test_tick_skips_when_llm_exceeds_timeout(monkeypatch):
    """A slow llm_fn must not park the loop forever — wait_for raises
    TimeoutError, the tick is skipped, no command is submitted.

    Timing must be measured *inside* the coroutine: asyncio.run() waits
    for the default thread executor to drain on shutdown, so the slow
    worker thread keeps the outer asyncio.run() blocked even after the
    coroutine has long since returned."""
    monkeypatch.setattr(runner, "AGENT_LLM_TIMEOUT_SECONDS", 0.1)
    monkeypatch.setattr(runner, "_snapshot", lambda _actor: {"_": None})
    monkeypatch.setattr(runner, "build_user_prompt", lambda _snap: "look")

    def slow_llm(_system: str, _user: str) -> str:
        time.sleep(0.5)
        return "n"

    world_loop = _FakeLoop()
    actor = _fake_actor()

    async def _measure() -> float:
        started = time.monotonic()
        await runner._tick_once(world_loop, actor, slow_llm)
        return time.monotonic() - started

    elapsed = asyncio.run(_measure())

    assert elapsed < 0.4, f"_tick_once parked for {elapsed:.2f}s — timeout didn't fire"
    assert world_loop.submitted == []


def test_tick_submits_command_on_normal_reply(monkeypatch):
    """Sanity: a fast llm_fn flows through to submit_command with the
    parsed command echoed."""
    monkeypatch.setattr(runner, "AGENT_LLM_TIMEOUT_SECONDS", 5.0)
    monkeypatch.setattr(runner, "_snapshot", lambda _actor: {"_": None})
    monkeypatch.setattr(runner, "build_user_prompt", lambda _snap: "look")

    world_loop = _FakeLoop()
    actor = _fake_actor()

    asyncio.run(runner._tick_once(world_loop, actor, lambda s, u: "n"))

    assert world_loop.submitted == [("agent_test", "n")]


# ── Combat prompt + fallback ──

class _FakeRoom:
    id = "room_1"


def _combat_actor(abilities=("attack", "defend")):
    state = SimpleNamespace(
        name="Grosh", race="Half-Orc", agent_class="Warrior", level=1,
        hp=12, max_hp=12, mp=0, max_mp=0, ap=10, max_ap=10,
        abilities=list(abilities), action_history=[], world_id="default",
        room_id="room_1", game_clock={"minute": 480},
    )
    return SimpleNamespace(actor_id="agent_test", state=state,
                           agent_def={"system_prompt": "be brief"})


def test_combat_prompt_lists_actual_abilities_and_strips_exits():
    """Combat prompt must enumerate the agent's abilities literally
    (so the LLM doesn't have to invent them) and must NOT show exits
    (which would tempt movement, which doesn't work in combat)."""
    actor = _combat_actor(abilities=("attack", "defend", "smite", "lay_on_hands"))
    snap = {"state": actor.state, "room": None, "in_combat": True}
    prompt = runner.build_user_prompt(snap)
    assert "Combat commands available: attack, defend, smite, lay_on_hands, flee" in prompt
    assert "YOU ARE IN COMBAT" in prompt
    assert "Exits:" not in prompt
    # Sanity: explore-mode help text doesn't leak in
    assert "n/s/e/w/up/down" not in prompt


def test_coerce_combat_substitutes_attack_for_movement(monkeypatch):
    """LLM picks `north` while in combat — fallback turns it into
    `attack <first hostile>` so the round actually advances."""
    actor = _combat_actor()
    fake_mob = SimpleNamespace(name="Wild Boar", hp=10, max_hp=10)
    monkeypatch.setattr(runner.world_store, "mobs_in_room",
                        lambda _w, _r, alive_only=True: [fake_mob])
    snap = {"state": actor.state, "room": _FakeRoom(), "in_combat": True}
    out = runner._coerce_combat_command("north", actor, snap)
    assert out == "attack Wild Boar"


def test_coerce_combat_passes_through_valid_ability():
    """If the LLM picks a real ability, leave it alone."""
    actor = _combat_actor(abilities=("attack", "smite"))
    snap = {"state": actor.state, "room": _FakeRoom(), "in_combat": True}
    assert runner._coerce_combat_command("smite Wild Boar", actor, snap) == "smite Wild Boar"
    assert runner._coerce_combat_command("attack Wild Boar", actor, snap) == "attack Wild Boar"
    assert runner._coerce_combat_command("flee", actor, snap) == "flee"
