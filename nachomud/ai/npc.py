"""NPC dialogue: prompt building, LLM call, lore summarization.

NPCs respond in character based on their personality, title, current activity,
and the player's stated message. The full NPC reply is shown to the player
in real time; a 1-2 sentence summary (via the fast/summary model) is appended
to the player's `lore_history` so the long body doesn't crowd context windows
in future prompts.

LLM and summary callers are dependency-injected so tests can stub them.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from collections.abc import Callable

from nachomud.ai.contexts import load as load_context
from nachomud.ai.llm import LLMUnavailable
from nachomud.settings import LLM_SMART_MODEL, LLM_SUMMARY_MODEL, LORE_HISTORY_SIZE
from nachomud.models import AgentState, NPC


log = logging.getLogger("nachomud.npc")

LLMFn = Callable[[str, str], str]
"""(system_prompt, user_prompt) -> reply"""


def _default_llm(host: str | None = None) -> LLMFn:
    """Smart-model NPC dialogue. `host` matches the actor's DM host
    (player's tailnet Ollama for humans, operator for agents) — NPC
    dialogue is the same tier as the DM, so it routes the same place."""
    def _call(system: str, user: str) -> str:
        from nachomud.ai.llm import chat
        return chat(system=system, message=user, model=LLM_SMART_MODEL,
                    host=host, max_tokens=300)
    return _call


def _default_summary(host: str | None = None) -> LLMFn:
    """Summary tier — fast model. Routes to the same host as the dialogue
    call so an off-GPU player doesn't have one of two NPC calls succeed."""
    def _call(system: str, user: str) -> str:
        from nachomud.ai.llm import chat
        return chat(system=system, message=user, model=LLM_SUMMARY_MODEL,
                    host=host, max_tokens=120)
    return _call


# ── Prompts ──
# Templates live in nachomud/contexts/*.md — edit there, not here.
# npc_dialogue.md keeps {name}/{title}/{personality}/{activity} placeholders
# that build_npc_system() fills in per-NPC.

NPC_PERSONA_TEMPLATE = load_context("npc_dialogue")
SUMMARY_PERSONA = load_context("npc_summary")


def build_npc_system(npc: NPC, activity: str) -> str:
    first = npc.name.split()[0] if npc.name else "me"
    return NPC_PERSONA_TEMPLATE.format(
        name=npc.name, title=npc.title,
        personality=npc.personality or "You are a stoic, taciturn local.",
        activity=activity or "going about your day",
        first_name=first,
    )


def build_npc_user_prompt(npc: NPC, player: AgentState, message: str) -> str:
    parts = [f"A traveler approaches you. They are {player.name}, a {player.race} {player.agent_class}."]
    if npc.wares:
        parts.append("\nYour wares for sale (use these EXACTLY — do not invent items or prices):")
        for w in npc.wares:
            parts.append(f"  - {w['name']} — {w.get('price', 0)} gp")

    # Per-NPC conversation history so the NPC can build on prior exchanges
    history = _get_npc_chat_history(player, npc)
    history_blob = " ".join((ex.get("npc", "") or "").lower() for ex in history)
    if history:
        parts.append("\nYour recent conversation with this person (do not repeat your earlier greetings or phrasing):")
        for ex in history[-6:]:
            parts.append(f"  Them: {ex.get('player', '')}")
            parts.append(f"  You:  {ex.get('npc', '')}")
        parts.append("Build on what was said. Reference an earlier turn if natural.")

    # Lore: facts you know. The NPC should pick a fact they HAVEN'T already
    # mentioned in this conversation (cross-checked against history above).
    if npc.lore:
        parts.append("\nFacts you know (your private knowledge — share them with the player as the conversation warrants, ONE per turn). Mark which you've already shared by checking the history above:")
        for fact in npc.lore:
            already = "  [ALREADY SHARED]" if _fact_in_history(fact, history_blob) else ""
            parts.append(f"  - {fact}{already}")
        parts.append("If they ask an open question or you'd otherwise repeat yourself, "
                     "share an UNTOLD fact from this list. Once you've shared them all, "
                     "say so honestly: 'I've told you everything I know, friend.'")

    parts.append(f"\nThey now say: {message}\n\nReply in character (1-3 sentences). "
                 f"If this is a repeat visit, vary your greeting and add a new detail.")
    return "\n".join(parts)


def _fact_in_history(fact: str, history_blob: str) -> bool:
    """Crude overlap check — if 3+ distinctive words from the fact appear in
    the recent NPC dialogue, treat it as already shared."""
    if not history_blob:
        return False
    # Use distinctive keywords from the fact (long enough to be meaningful)
    keywords = [w.lower().strip(".,;:'\"!?") for w in fact.split()
                if len(w) >= 5 and w.lower() not in {"about", "their", "there",
                "where", "which", "those", "these", "would", "could", "should"}]
    if len(keywords) < 3:
        return False
    hits = sum(1 for kw in keywords if kw in history_blob)
    return hits >= 3


def _get_npc_chat_history(player: AgentState, npc: NPC) -> list[dict]:
    chats = (player.dm_context or {}).get("npc_chats") or {}
    return list(chats.get(npc.npc_id or npc.name, []))


def _record_npc_chat(player: AgentState, npc: NPC, player_msg: str, npc_reply: str,
                     cap: int = 8) -> None:
    if not npc.npc_id and not npc.name:
        return
    key = npc.npc_id or npc.name
    ctx = player.dm_context or {}
    chats = ctx.get("npc_chats") or {}
    history = list(chats.get(key, []))
    history.append({"player": player_msg, "npc": npc_reply})
    history = history[-cap:]
    chats[key] = history
    ctx["npc_chats"] = chats
    player.dm_context = ctx


def build_summary_user_prompt(npc_name: str, dialogue: str) -> str:
    return (
        f"NPC {npc_name} just said: \"{dialogue}\"\n\n"
        f"Compress to 1-2 sentences for the lore log."
    )


# ── Public API ──

@dataclass
class NPCDialogue:
    llm: LLMFn | None = None
    summarizer: LLMFn | None = None
    host: str | None = None

    def __post_init__(self):
        if self.llm is None:
            self.llm = _default_llm(host=self.host)
        if self.summarizer is None:
            self.summarizer = _default_summary(host=self.host)

    def speak(self, player: AgentState, npc: NPC, activity: str, message: str) -> tuple[str, str]:
        """Get the NPC's reply and a 1-2 sentence summary. Both are returned;
        the caller decides what to display vs. log."""
        # Deterministic short-circuit for "what do you sell?" — same harmony
        # rule as the DM: if the engine knows the answer, never let the LLM
        # invent it.
        canned = _try_canned_npc_reply(npc, message)
        if canned is not None:
            self._record_lore(player, npc, canned)
            _record_npc_chat(player, npc, message, canned)
            return canned, ""

        system = build_npc_system(npc, activity)
        user = build_npc_user_prompt(npc, player, message)
        try:
            reply = self.llm(system, user).strip()
        except LLMUnavailable as e:
            log.warning("NPC.speak unavailable for %s talking to %s: %s",
                        player.player_id, npc.name, e)
            return f"({npc.name} doesn't seem to hear you.)", ""
        except Exception:
            log.exception("NPC.speak LLM call failed")
            return f"({npc.name} doesn't seem to hear you.)", ""

        # Summary (best-effort; skip if it fails)
        try:
            summary = self.summarizer(SUMMARY_PERSONA, build_summary_user_prompt(npc.name, reply)).strip()
        except Exception:
            summary = f"{npc.name}: {reply[:140]}"

        # Append to player's lore history (with rolling cap)
        if summary:
            self._record_lore(player, npc, summary)
        _record_npc_chat(player, npc, message, reply)

        return reply, summary

    def _record_lore(self, player: AgentState, npc: NPC, line: str) -> None:
        player.lore_history.append(f"{npc.name}: {line}")
        if len(player.lore_history) > LORE_HISTORY_SIZE:
            player.lore_history = player.lore_history[-LORE_HISTORY_SIZE:]


# ── NPC deterministic short-circuits ──

_NPC_WARES_KEYWORDS = (
    "what do you sell", "what do you have", "what's for sale", "what kind of",
    "wares", "stock", "got any", "have for sale", "what sort of", "what have you got",
    "for sale", "selling",
)


def _try_canned_npc_reply(npc: NPC, message: str) -> str | None:
    if not npc.wares:
        return None
    msg = (message or "").lower()
    if not any(kw in msg for kw in _NPC_WARES_KEYWORDS):
        return None
    items = ", ".join(f"{w['name']} ({w.get('price', 0)} gp)" for w in npc.wares)
    first = npc.name.split()[0] if npc.name else npc.name
    return (f"I've got {items}. Type `buy <item> from {first}` if you want any.")
