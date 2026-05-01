"""Schema migration dispatch.

Each entity (player, room, mob, item, graph) carries a `schema_version` int.
When a payload is loaded with an older version, the migration registry walks
it forward step by step until it matches the current version.

To add a migration:
    @register("player", from_version=1)
    def player_v1_to_v2(payload: dict) -> dict:
        payload["new_field"] = ...
        return payload  # caller bumps version
"""
from __future__ import annotations

from collections.abc import Callable

# (entity, from_version) -> migration function (returns updated payload at from+1)
_REGISTRY: dict[tuple[str, int], Callable[[dict], dict]] = {}


def register(entity: str, from_version: int):
    def deco(fn: Callable[[dict], dict]) -> Callable[[dict], dict]:
        _REGISTRY[(entity, from_version)] = fn
        return fn
    return deco


def migrate(entity: str, payload: dict, target_version: int) -> dict:
    """Walk `payload` forward to `target_version` via registered migrations."""
    current = int(payload.get("schema_version", 1))
    while current < target_version:
        fn = _REGISTRY.get((entity, current))
        if fn is None:
            raise ValueError(
                f"No migration registered for {entity} schema v{current} → v{current + 1}"
            )
        payload = fn(payload)
        current += 1
        payload["schema_version"] = current
    return payload
