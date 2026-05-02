"""Registered migrations for the player schema."""
from __future__ import annotations

from nachomud.characters.migrations import register


@register("player", from_version=1)
def player_v1_to_v2(payload: dict) -> dict:
    """v2 adds `dm_ollama_url` (per-character DM-tier Ollama URL).

    Existing characters predate per-player BYO-GPU and have no URL set.
    They keep working as spectators / explorers, but DM calls surface
    'the world feels still' until they set one (future: a `/dm-host`
    slash command, or by re-creating the character)."""
    payload.setdefault("dm_ollama_url", "")
    return payload
