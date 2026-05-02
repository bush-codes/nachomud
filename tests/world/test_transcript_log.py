"""Tests for world/transcript_log.py — per-actor JSONL persistence."""
from __future__ import annotations

import time

import nachomud.world.transcript_log as tlog


def test_append_then_read_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(tlog, "DATA_ROOT", str(tmp_path))
    tlog.append("agent_test", ("output", "hello\r\n"))
    tlog.append("agent_test", ("prompt", "you> "))
    tlog.append("agent_test", {"type": "status", "hp": 10, "max_hp": 10})

    history = tlog.read_recent("agent_test")
    assert len(history) == 3
    # Tuple-shaped events come back as tuples (not lists).
    assert history[0] == ("output", "hello\r\n")
    assert history[1] == ("prompt", "you> ")
    # Dict-shaped events round-trip as dicts.
    assert history[2] == {"type": "status", "hp": 10, "max_hp": 10}


def test_read_drops_entries_older_than_window(tmp_path, monkeypatch):
    """Spectators connecting see a 24h window — older entries omitted."""
    monkeypatch.setattr(tlog, "DATA_ROOT", str(tmp_path))
    # Hand-write one OLD entry + one fresh one, bypassing append() to
    # control the timestamp.
    path = tmp_path / "agent_test.jsonl"
    old_ts = time.time() - 48 * 3600
    fresh_ts = time.time() - 60
    path.write_text(
        f'{{"ts": {old_ts}, "item": ["output", "ancient\\r\\n"]}}\n'
        f'{{"ts": {fresh_ts}, "item": ["output", "recent\\r\\n"]}}\n'
    )
    history = tlog.read_recent("agent_test", max_age_seconds=24 * 3600)
    assert history == [("output", "recent\r\n")]


def test_read_returns_empty_for_unknown_actor(tmp_path, monkeypatch):
    monkeypatch.setattr(tlog, "DATA_ROOT", str(tmp_path))
    assert tlog.read_recent("never_existed") == []


def test_append_swallows_disk_errors(tmp_path, monkeypatch):
    """A broken disk path must not crash the world loop. We point at
    a non-writeable path and verify append() silently drops."""
    monkeypatch.setattr(tlog, "DATA_ROOT", "/dev/null/cannot-write-here")
    tlog.append("agent_test", ("output", "hello\r\n"))  # must not raise


def test_corrupt_lines_are_skipped(tmp_path, monkeypatch):
    """Garbage lines in the middle of the log don't kill the read."""
    monkeypatch.setattr(tlog, "DATA_ROOT", str(tmp_path))
    path = tmp_path / "agent_test.jsonl"
    fresh_ts = time.time() - 60
    path.write_text(
        f'{{"ts": {fresh_ts}, "item": ["output", "first\\r\\n"]}}\n'
        'this is not json\n'
        '{"ts": "garbage", "item": ["output", "broken ts\\r\\n"]}\n'
        f'{{"ts": {fresh_ts}, "item": ["output", "third\\r\\n"]}}\n'
    )
    history = tlog.read_recent("agent_test")
    # The two valid entries survive; garbage skipped (the "garbage ts"
    # line raises in float() and is also skipped).
    assert history == [("output", "first\r\n"), ("output", "third\r\n")]
