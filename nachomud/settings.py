"""Runtime configuration: env-var lookups + game-tuning constants.

Game rules (race/class/ability/leveling tables) live in nachomud.rules.
This module only carries values that change between deployments or
runs.
"""
from __future__ import annotations

import os


# ── LLM backend ──
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
LLM_BACKEND = os.environ.get("LLM_BACKEND", "ollama")
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")

# Player-mode model split. All Llama, no Qwen.
LLM_SMART_MODEL = os.environ.get("LLM_SMART_MODEL", "llama3.1:8b-instruct-q4_K_M")
LLM_FAST_MODEL = os.environ.get("LLM_FAST_MODEL", "llama3.2:3b")
LLM_SUMMARY_MODEL = os.environ.get("LLM_SUMMARY_MODEL", "llama3.2:3b")


# ── Game tunables ──
QUEST_DESCRIPTION = "Explore Silverbrook and the wild beyond. Talk to NPCs for lore, gear up, and forge your own story."

ACTION_HISTORY_SIZE = 12
COMM_HISTORY_SIZE = 5
LORE_HISTORY_SIZE = 3

DM_RECENT_EXCHANGES_CAP = 30  # rolling DM conversation window

# Player-mode XP penalty on death
DEATH_XP_PENALTY_PCT = 0.10

# Starting gold for new characters
STARTING_GOLD = 25

# Seconds between agent ticks (per agent — staggered across the four).
# Lower = livelier agents, more LLM load. On a CPU-only host like
# Lightsail you'll want 30-60s to keep up; with GPU inference 5-10s
# is fine.
AGENT_TICK_SECONDS = float(os.environ.get("NACHOMUD_AGENT_TICK_SECONDS", "8"))

# Hard ceiling on how long an agent waits for the LLM before skipping a
# tick. Without this, a wedged Ollama (memory pressure, model swap,
# network blip) parks the agent's asyncio task forever.
AGENT_LLM_TIMEOUT_SECONDS = float(
    os.environ.get("NACHOMUD_AGENT_LLM_TIMEOUT", "30")
)
