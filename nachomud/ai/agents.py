"""Built-in AI agent personalities.

The four LLM-driven agents that exist in every world: Aelinor the Scholar,
Grosh the Berserker, Pippin the Wanderer, Brother Calder the Zealot.

Personalities are data, not code. The agent runner reads `system_prompt`
to flavor each agent's LLM-driven command choice. Add or tune them by
editing this list and the corresponding `contexts/agent_*.md` file.
"""
from __future__ import annotations

from nachomud.ai.contexts import load as _load_context
from nachomud.characters.character import create_character
from nachomud.models import AgentState
from nachomud.rules.stats import STAT_NAMES, Stats


# ── Built-in agent personalities ──
#
# Each entry produces one fixed agent that exists in every world.
# Player IDs are stable: data/players/agent_<id>.json. If the file
# already exists on disk we load it instead of re-minting.

AGENT_DEFINITIONS: list[dict] = [
    {
        "actor_id": "agent_scholar",
        "display_name": "The Scholar",
        "name": "Aelinor",
        "race": "Elf",
        "class_name": "Mage",
        "primary": "INT",
        "system_prompt": _load_context("agent_scholar"),
    },
    {
        "actor_id": "agent_berserker",
        "display_name": "The Berserker",
        "name": "Grosh",
        "race": "Half-Orc",
        "class_name": "Warrior",
        "primary": "STR",
        "system_prompt": _load_context("agent_berserker"),
    },
    {
        "actor_id": "agent_wanderer",
        "display_name": "The Wanderer",
        "name": "Pippin",
        "race": "Halfling",
        "class_name": "Ranger",
        "primary": "DEX",
        "system_prompt": _load_context("agent_wanderer"),
    },
    {
        "actor_id": "agent_zealot",
        "display_name": "The Zealot",
        "name": "Brother Calder",
        "race": "Human",
        "class_name": "Paladin",
        "primary": "STR",
        "system_prompt": _load_context("agent_zealot"),
    },
]


def _stats_for(class_name: str, primary: str) -> Stats:
    """Standard array (15,14,13,12,10,8) with primary stat first."""
    order = [primary] + [s for s in STAT_NAMES if s != primary]
    values = [15, 14, 13, 12, 10, 8]
    s = Stats()
    for stat, v in zip(order, values, strict=False):
        s.set(stat, v)
    return s


def build_agent_state(definition: dict, *, world_id: str, spawn_room: str) -> AgentState:
    """Mint a fresh AgentState for a built-in agent. Called by WorldLoop
    the first time the agent's save file doesn't exist on disk."""
    state = create_character(
        name=definition["name"],
        race=definition["race"],
        class_name=definition["class_name"],
        base_stats=_stats_for(definition["class_name"], definition["primary"]),
        level=1,
        player_id=definition["actor_id"],
        respawn_room=spawn_room,
        world_id=world_id,
    )
    state.personality = definition.get("system_prompt", "")
    state.room_id = spawn_room
    if spawn_room and spawn_room not in state.visited_rooms:
        state.visited_rooms.append(spawn_room)
    return state
