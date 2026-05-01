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
