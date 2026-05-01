"""External context/prompt files.

Personas and templates for the DM, NPCs, and the four AI agents are kept
here as Markdown files so they can be edited and iterated on without
touching Python (and so they render nicely on GitHub).

`_shared.md` is a parent context auto-prepended to every loaded file —
it carries the world setting, content rating, and relevance/voice rules
that apply to every AI in the game.

Files are identified by stem (no extension):
    dm_persona, dm_adjudicate, dm_room_gen,
    npc_dialogue, npc_summary,
    agent_scholar, agent_berserker, agent_wanderer, agent_zealot

Reading is cached per-process — restart the server to pick up edits.
Tests can call `load.cache_clear()` to force a re-read.
"""
from __future__ import annotations

import os
from functools import cache


_CONTEXT_DIR = os.path.dirname(os.path.abspath(__file__))


def _read(name: str) -> str:
    path = os.path.join(_CONTEXT_DIR, f"{name}.md")
    with open(path, encoding="utf-8") as f:
        return f.read().rstrip("\n")


@cache
def load(name: str) -> str:
    """Read context file `<name>.md`. For all names other than `_shared`,
    the contents of `_shared.md` are prepended (so every prompt inherits
    the world rules, content rating, etc.). Cached per-process."""
    body = _read(name)
    if name == "_shared":
        return body
    return f"{_read('_shared')}\n\n---\n\n{body}"
