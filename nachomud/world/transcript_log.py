"""Per-actor transcript persistence.

`Actor.transcript` was an in-memory ring buffer (200 entries) that
disappeared on container restart, so spectators connecting to an agent
saw only events from "now forward." Persistent JSONL log per actor,
read with a 24h window on subscribe, gives the spectator real history.

Each line in `<actor_id>.jsonl` is `{"ts": <unix>, "item": <event>}`.
`<event>` is either a 2-element list (the (kind, payload) tuple as
JSON) or a dict (status-style events). On read we coerce the list
back to a tuple so downstream code keeps working unchanged.

Disk size is bounded by traffic, not retention — we DON'T trim on
write. With ~12 commands/min across 4 agents, that's ~tens of KB/hour.
A periodic trim (drop entries older than 24h) is left for later.
"""
from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path

log = logging.getLogger("nachomud.transcriptlog")

# Default to <data>/transcripts/. Tests override via the env var.
DATA_ROOT = os.environ.get(
    "NACHOMUD_TRANSCRIPT_ROOT",
    os.path.join(os.environ.get("NACHOMUD_DATA_ROOT", "data"), "transcripts"),
)

# Spectators see this much history when they subscribe to an actor.
DEFAULT_REPLAY_SECONDS = 24 * 3600


def _path(actor_id: str) -> Path:
    root = Path(DATA_ROOT)
    root.mkdir(parents=True, exist_ok=True)
    return root / f"{actor_id}.jsonl"


def append(actor_id: str, item) -> None:
    """Append a single transcript event to the actor's log. Errors
    are swallowed (logged) — disk hiccups must not break the world
    loop. `item` is whatever Actor.record() received: usually a
    (kind, payload) tuple or a status-style dict."""
    payload = list(item) if isinstance(item, tuple) else item
    record = {"ts": time.time(), "item": payload}
    try:
        with _path(actor_id).open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, default=str) + "\n")
    except Exception:
        log.exception("transcript append failed for %s", actor_id)


def read_recent(actor_id: str,
                *, max_age_seconds: float = DEFAULT_REPLAY_SECONDS) -> list:
    """Return events from the last `max_age_seconds`, oldest first.
    Tuples-stored-as-lists are coerced back to tuples so callers can
    enqueue them without converting."""
    path = _path(actor_id)
    if not path.exists():
        return []
    cutoff = time.time() - max_age_seconds
    out: list = []
    try:
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                    if not isinstance(rec, dict):
                        continue
                    if float(rec.get("ts", 0)) < cutoff:
                        continue
                    item = rec.get("item")
                    if isinstance(item, list):
                        item = tuple(item)
                    out.append(item)
                except Exception:
                    # One bad line doesn't kill the whole replay.
                    continue
    except Exception:
        log.exception("transcript read failed for %s", actor_id)
        return []
    return out
