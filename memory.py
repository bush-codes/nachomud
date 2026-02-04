from __future__ import annotations

import json
import os

from config import MAX_MEMORY_ENTRIES, MEMORY_DIR


def _memory_path(agent_name: str) -> str:
    return os.path.join(MEMORY_DIR, f"{agent_name.lower()}.json")


def load_memories(agent_name: str) -> list[dict]:
    path = _memory_path(agent_name)
    if not os.path.exists(path):
        return []
    with open(path) as f:
        data = json.load(f)
    return data.get("entries", [])


def save_memories(agent_name: str, entries: list[dict]) -> None:
    os.makedirs(MEMORY_DIR, exist_ok=True)
    path = _memory_path(agent_name)
    with open(path, "w") as f:
        json.dump({"agent": agent_name, "entries": entries}, f, indent=2)


def append_memory(agent_name: str, tick: int, summary: str) -> None:
    entries = load_memories(agent_name)
    entries.append({"tick": tick, "summary": summary})

    if len(entries) > MAX_MEMORY_ENTRIES:
        # Condense oldest entries into a single early-history summary
        old = entries[: len(entries) - MAX_MEMORY_ENTRIES + 1]
        condensed = "Earlier: " + " | ".join(e["summary"] for e in old[-5:])
        entries = [{"tick": 0, "summary": condensed}] + entries[len(entries) - MAX_MEMORY_ENTRIES + 1 :]

    save_memories(agent_name, entries)


def clear_memories(agent_name: str) -> None:
    path = _memory_path(agent_name)
    if os.path.exists(path):
        os.remove(path)


def format_memories_for_prompt(agent_name: str) -> str:
    entries = load_memories(agent_name)
    if not entries:
        return "No memories yet. This is your first moment in the dungeon."
    lines = []
    for e in entries[-10:]:
        lines.append(f"- {e['summary']}")
    return "\n".join(lines)


def build_narrative_memory(agent_name: str, events: list, room_name: str) -> str:
    """Build a concise narrative memory from this tick's events."""
    parts = []
    for e in events:
        result = e.result.split("\n")[0]
        # Condense repetitive or empty results
        if "Unknown command" in result:
            continue
        if result.startswith("Room:"):
            continue
        parts.append(result)

    if not parts:
        return ""

    # Build a short narrative
    summary = f"[{room_name}] " + " ".join(parts)
    if len(summary) > 200:
        summary = summary[:197] + "..."
    return summary
