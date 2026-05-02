"""The Dungeon Master.

Phase 5 ships the conversational stub: handles `dm <message>` and free-form
fall-through input from the player.

Phase 9 adds the world generator: `generate_room()` turns an unexplored exit
into a frozen room with NPCs, mobs, and items, persisted across all three
stores. Generated rooms can have additional placeholder exits which trigger
further generation when the player walks them.

Phase 10 will add adjudication (skill checks / state mutations), conjuring
with side effects, and unprompted interjections.

The LLM call is abstracted so tests can inject a stub.
"""
from __future__ import annotations

import json
import logging
import re
import uuid
from dataclasses import dataclass
from collections.abc import Callable

import nachomud.world.store as world_store
from nachomud.ai.world_gen import WorldGen, _extract_json
from nachomud.ai.llm import LLMUnavailable
from nachomud.ai.contexts import load as load_context
from nachomud.settings import DM_RECENT_EXCHANGES_CAP, LLM_SMART_MODEL
from nachomud.models import AgentState, Item, Mob, Room

log = logging.getLogger("nachomud.dm")

# Personas live in nachomud/contexts/*.md — edit there, not here.
DM_PERSONA = load_context("dm_persona")
ADJUDICATE_PERSONA = load_context("dm_adjudicate")


# ── LLM caller (DI for tests) ──

LLMFn = Callable[[str, str], str]
"""Type: (system_prompt, user_prompt) -> assistant_reply"""


def _default_llm() -> LLMFn:
    """Default LLM caller: Ollama via the existing llm.chat helper."""
    def _call(system: str, user: str) -> str:
        # Lazy import so test environments without ollama installed still load this module
        from nachomud.ai.llm import chat
        return chat(system=system, message=user, model=LLM_SMART_MODEL, max_tokens=400)
    return _call


# ── Context management ──

def _ctx_for(player: AgentState) -> dict:
    return player.dm_context or {"recent_exchanges": [], "summary": "", "pending_hints": []}


def _trim(exchanges: list[dict], cap: int = DM_RECENT_EXCHANGES_CAP) -> list[dict]:
    return exchanges[-cap:]


# ── Prompt building ──

def _build_user_prompt(player: AgentState, room: Room, message: str) -> str:
    ctx = _ctx_for(player)
    recent = ctx.get("recent_exchanges", [])
    summary = ctx.get("summary", "")

    parts = []
    parts.append(f"Player character: {player.name} the {player.race} {player.agent_class} (L{player.level}).")
    parts.append(f"Current room: {room.name} — {room.description}")
    if room.exits:
        parts.append(f"Visible exits: {', '.join(sorted(room.exits.keys()))}")

    # Live presence: who and what is ACTUALLY in this room right now.
    # The DM must not invent additional NPCs or mobs — only describe these.
    presence_lines = _presence_summary(player, room)
    if presence_lines:
        parts.append("\nWho/what is present in this room RIGHT NOW (do not invent others):")
        parts.extend(f"  - {line}" for line in presence_lines)
    else:
        parts.append("\nNo one else is here right now (do not invent NPCs or creatures).")

    # Wares from any present shopkeeper, so the DM can answer "what does X sell?"
    shop_lines = _wares_summary(player, room)
    if shop_lines:
        parts.append("\nWares for sale by present shopkeepers (use these — do not invent prices or items):")
        parts.extend(f"  - {line}" for line in shop_lines)
    parts.append(f"\nPlayer's gold: {player.gold} gp.")

    if summary:
        parts.append(f"\nJourney so far: {summary}")

    # Surface pending hints so the DM can reference its own forward-looking
    # promises ("you mentioned an inn 2 north — they're following up").
    pending_hints = (ctx or {}).get("pending_hints") or []
    if pending_hints:
        parts.append("\nWorld facts you've already promised the player (reference these "
                     "naturally if relevant; do NOT contradict them):")
        for h in pending_hints[-5:]:
            parts.append(f"  - {h.get('hint', '')}")

    if recent:
        parts.append("\nRecent conversation:")
        for ex in recent[-6:]:  # last few turns only in prompt
            parts.append(f"  Player: {ex.get('player', '')}")
            parts.append(f"  DM: {ex.get('dm', '')}")
    parts.append(f"\nThe player says/asks: {message}")
    parts.append("\nRespond in character as the DM (1-3 sentences). "
                 "Stay grounded in the people/items listed above — do not "
                 "introduce NPCs or creatures that aren't on that list.")
    return "\n".join(parts)


def _presence_summary(player: AgentState, room: Room) -> list[str]:
    """Compact list of every visible NPC, mob, and item in the player's room
    right now (NPCs filtered through the routine projection)."""
    from nachomud.world.routines import hour_from_minute, npcs_in_room
    lines: list[str] = []
    hour = hour_from_minute((player.game_clock or {}).get("minute", 480))
    for npc, activity in npcs_in_room(room.npcs, room.id, hour):
        suffix = f" ({activity})" if activity else ""
        lines.append(f"NPC {npc.name} the {npc.title}{suffix}")
    try:
        for m in world_store.mobs_in_room(player.world_id, room.id, alive_only=True):
            lines.append(f"Mob {m.name} (HP {m.hp}/{m.max_hp})")
        for it in world_store.items_in_room(player.world_id, room.id):
            lines.append(f"Item {it.get('name', 'unknown')}")
    except Exception:
        pass
    return lines


# ── Public API ──

@dataclass
class DM:
    llm: LLMFn | None = None
    world_gen: WorldGen | None = None

    def __post_init__(self):
        if self.llm is None:
            self.llm = _default_llm()
        if self.world_gen is None:
            self.world_gen = WorldGen(llm=self.llm)

    def respond(self, player: AgentState, room: Room, message: str) -> str:
        """Generate a DM reply and append it to the player's rolling context.
        Extracts inline HINT: tags and persists them as pending_hints. If the
        message matches a deterministic intent (commerce wares query), short-
        circuits to a canned response so the small LLM can't hallucinate
        prices or items."""
        canned = _try_deterministic_reply(player, room, message)
        if canned is not None:
            reply = canned
        else:
            prompt = _build_user_prompt(player, room, message)
            try:
                reply = self.llm(DM_PERSONA, prompt).strip()
            except LLMUnavailable:
                # Don't pollute dm_context with the failure — let the
                # player retry once the LLM is back.
                return "(The DM is silent for the moment — the world feels still.)"
            except Exception as e:
                log.exception("DM.respond LLM call failed")
                reply = f"(The DM's voice falters momentarily — {type(e).__name__}.)"
        cleaned, hint = _extract_hint(reply)
        ctx = _ctx_for(player)
        ctx.setdefault("recent_exchanges", [])
        ctx["recent_exchanges"].append({"player": message, "dm": cleaned})
        ctx["recent_exchanges"] = _trim(ctx["recent_exchanges"])
        if hint:
            ctx.setdefault("pending_hints", [])
            ctx["pending_hints"].append({"hint": hint, "added_at_room": room.id})
        player.dm_context = ctx
        return cleaned

    def adjudicate(self, player: AgentState, room: Room, action: str) -> dict:
        """Adjudicate a free-form player action. Returns a dict with:
          - narrate: str
          - skill_check_result: optional dict {stat, dc, roll, total, success, narration}
          - hint: optional str (also written to pending_hints)

        Short-circuits to a deterministic answer for common factual queries
        (wares, prices) so the small LLM can't invent state.
        """
        canned = _try_deterministic_reply(player, room, action)
        if canned is not None:
            payload = {"narrate": canned, "skill_check": None, "hint": None, "actions": None}
        else:
            prompt = _build_adjudicate_prompt(player, room, action)
            try:
                raw = self.llm(ADJUDICATE_PERSONA, prompt)
                payload = _extract_json(raw)
            except LLMUnavailable:
                payload = {"narrate": "You attempt the action, but the world feels paused — try again in a moment.",
                           "skill_check": None, "hint": None, "actions": None}
            except Exception:
                log.exception("DM.adjudicate LLM call failed")
                payload = {"narrate": f"You attempt to {action}, but the gesture comes to nothing.",
                           "skill_check": None, "hint": None, "actions": None}

        narrate = str(payload.get("narrate", "")).strip()
        sc_result = None
        sc = payload.get("skill_check")
        if sc and isinstance(sc, dict):
            sc_result = self._resolve_skill_check(player, sc)

        # Apply DM-requested state actions. Only run "on success" actions if a
        # skill check was made and succeeded; if no check, actions always run.
        applied: list[dict] = []
        actions_spec = payload.get("actions") or []
        if isinstance(actions_spec, dict):
            actions_spec = [actions_spec]
        gate_open = (sc_result is None) or sc_result.get("success", False)
        if gate_open:
            for act in actions_spec:
                if not isinstance(act, dict):
                    continue
                result = self._apply_action(player, room, act)
                if result:
                    applied.append(result)

        hint = payload.get("hint")
        ctx = _ctx_for(player)
        ctx.setdefault("recent_exchanges", [])
        log_dm = narrate
        if sc_result:
            log_dm += " " + sc_result["narration"]
        ctx["recent_exchanges"].append({"player": action, "dm": log_dm})
        ctx["recent_exchanges"] = _trim(ctx["recent_exchanges"])
        if hint and isinstance(hint, str):
            ctx.setdefault("pending_hints", [])
            ctx["pending_hints"].append({"hint": hint, "added_at_room": room.id})
        player.dm_context = ctx

        return {
            "narrate": narrate,
            "skill_check_result": sc_result,
            "actions_applied": applied,
            "hint": hint if isinstance(hint, str) else None,
        }

    def interject(self, player: AgentState, room: Room, occasion: str, detail: str = "") -> str:
        """DM speaks unprompted at a key moment (level up, discovery, dawn/dusk).
        Records the interjection in dm_context for continuity."""
        try:
            user = (f"Occasion: {occasion}. {detail}\n"
                    f"Player: {player.name} the {player.race} {player.agent_class} (L{player.level}).\n"
                    f"Current room: {room.name}.\n"
                    f"Speak briefly (1-2 sentences) in character to mark the moment.")
            reply = self.llm(DM_PERSONA, user).strip()
        except Exception:
            log.exception("DM.interject LLM call failed")
            reply = f"(A hush falls over the world. {occasion}.)"
        cleaned, hint = _extract_hint(reply)
        ctx = _ctx_for(player)
        ctx.setdefault("recent_exchanges", [])
        ctx["recent_exchanges"].append({"player": f"[interjection: {occasion}]", "dm": cleaned})
        ctx["recent_exchanges"] = _trim(ctx["recent_exchanges"])
        if hint:
            ctx.setdefault("pending_hints", [])
            ctx["pending_hints"].append({"hint": hint, "added_at_room": room.id})
        player.dm_context = ctx
        return cleaned

    # ── State-mutating actions (DM-requested, engine-validated) ──

    def _apply_action(self, player: AgentState, room: Room, act: dict) -> dict | None:
        kind = str(act.get("type", "")).lower()
        if kind == "consume_item":
            return self._act_consume_item(player, act)
        if kind == "restore_hp":
            return self._act_restore(player, "hp", act)
        if kind == "restore_mp":
            return self._act_restore(player, "mp", act)
        if kind == "restore_ap":
            return self._act_restore(player, "ap", act)
        if kind == "set_flag":
            return self._act_set_flag(player, room, act)
        if kind == "engage_combat":
            return self._act_engage_combat(player, room, act)
        if kind == "get_item":
            return self._act_get_item(player, room, act)
        if kind == "drop_item":
            return self._act_drop_item(player, room, act)
        if kind == "equip_item":
            return self._act_equip_item(player, act)
        if kind == "buy_item":
            return self._act_buy_item(player, room, act)
        log.warning("DM requested unknown action type: %s", kind)
        return None

    def _act_get_item(self, player: AgentState, room: Room, act: dict) -> dict | None:
        from nachomud.world.store import item_from_dict
        name = str(act.get("item_name", "")).strip().lower()
        if not name:
            return None
        try:
            in_room = world_store.items_in_room(player.world_id, room.id)
        except Exception:
            return None
        match = next((i for i in in_room if name in i.get("name", "").lower()), None)
        if match is None:
            return None
        try:
            world_store.update_item_location(player.world_id, match["item_id"],
                                             f"inv:{player.player_id}")
        except Exception:
            return None
        item = item_from_dict(match)
        if item is not None:
            player.inventory.append(item)
        return {"type": "got", "item": match.get("name", "?")}

    def _act_drop_item(self, player: AgentState, room: Room, act: dict) -> dict | None:
        name = str(act.get("item_name", "")).strip().lower()
        if not name:
            return None
        target = next((it for it in player.inventory if name in it.name.lower()), None)
        if target is None:
            return None
        try:
            inv_items = world_store.items_in_inventory(player.world_id, player.player_id)
            for w_it in inv_items:
                if w_it.get("name", "").lower() == target.name.lower():
                    world_store.update_item_location(
                        player.world_id, w_it["item_id"], f"room:{room.id}"
                    )
                    break
        except Exception:
            log.exception("failed to persist drop")
        player.inventory.remove(target)
        return {"type": "dropped", "item": target.name}

    def _act_equip_item(self, player: AgentState, act: dict) -> dict | None:
        # Lazy import to avoid game ↔ dm circular dependency at module load
        from nachomud.engine.game import _equip_from_inventory
        name = str(act.get("item_name", "")).strip()
        if not name:
            return None
        result = _equip_from_inventory(player, name)
        if not result["ok"]:
            return None
        return {"type": "equipped", "item": result["item_name"], "slot": result["slot"]}

    def _act_buy_item(self, player: AgentState, room: Room, act: dict) -> dict | None:
        from nachomud.world.routines import hour_from_minute, npcs_in_room
        import uuid as _uuid
        item_name = str(act.get("item_name", "")).strip().lower()
        npc_name = str(act.get("npc_name", "")).strip().lower()
        if not item_name:
            return None
        hour = hour_from_minute((player.game_clock or {}).get("minute", 480))
        present = [(n, a) for n, a in npcs_in_room(room.npcs, room.id, hour) if n.wares]
        # Find the shopkeeper + ware
        for npc, _ in present:
            if npc_name and npc_name not in npc.name.lower():
                continue
            for w in npc.wares:
                if item_name in w["name"].lower():
                    price = int(w.get("price", 0))
                    if player.gold < price:
                        return None  # caller can narrate "you can't afford it"
                    spec = {k: v for k, v in w.items() if k != "price"}
                    from dataclasses import fields as _fields
                    from nachomud.models import Item
                    item = Item(**{k: v for k, v in spec.items()
                                   if k in {f.name for f in _fields(Item)}})
                    item_id = f"shop_{_uuid.uuid4().hex[:10]}"
                    try:
                        world_store.add_item(player.world_id, item_id, item,
                                             f"inv:{player.player_id}")
                    except Exception:
                        return None
                    player.inventory.append(item)
                    player.gold -= price
                    return {"type": "bought", "item": item.name, "from": npc.name,
                            "price": price}
        return None

    def _act_engage_combat(self, player: AgentState, room: Room, act: dict) -> dict | None:
        """The DM signals 'this action starts combat with X'. The actual
        Encounter is created by the caller (game.py) — we just validate
        the target is here and alive."""
        target = str(act.get("target", "")).strip()
        if not target:
            return None
        try:
            mobs = world_store.mobs_in_room(player.world_id, room.id, alive_only=True)
        except Exception:
            return None
        match = next((m for m in mobs if target.lower() in m.name.lower()), None)
        if not match:
            return None
        return {"type": "combat_intent", "target": match.name, "mob_id": match.mob_id}

    def _act_consume_item(self, player: AgentState, act: dict) -> dict | None:
        name = str(act.get("item_name", "")).strip().lower()
        if not name:
            return None
        for it in player.inventory:
            if name in it.name.lower():
                consumed = it
                player.inventory.remove(it)
                # Mark the world-item entry as consumed so it won't reappear
                try:
                    inv_items = world_store.items_in_inventory(player.world_id, player.player_id)
                    for w_it in inv_items:
                        if w_it.get("name", "").lower() == consumed.name.lower():
                            world_store.update_item_location(
                                player.world_id, w_it["item_id"], "consumed"
                            )
                            break
                except Exception:
                    log.exception("failed to mark consumed item in world store")
                return {"type": "consumed", "item": consumed.name}
        # DM tried to consume something the player doesn't have — ignore quietly
        return None

    def _act_restore(self, player: AgentState, stat: str, act: dict) -> dict | None:
        try:
            amount = int(act.get("amount", 0))
        except (TypeError, ValueError):
            return None
        amount = max(0, min(amount, 5))  # hard cap so a rogue LLM can't full-heal
        if amount == 0:
            return None
        if stat == "hp":
            actual = min(amount, player.max_hp - player.hp)
            player.hp += actual
        elif stat == "mp":
            actual = min(amount, player.max_mp - player.mp)
            player.mp += actual
        elif stat == "ap":
            actual = min(amount, player.max_ap - player.ap)
            player.ap += actual
        else:
            return None
        if actual <= 0:
            return None
        return {"type": "restored", "stat": stat.upper(), "amount": actual}

    def _act_set_flag(self, player: AgentState, room: Room, act: dict) -> dict | None:
        flag = str(act.get("flag", "")).strip()
        if not flag or not flag.replace("_", "").isalnum():
            return None
        value = bool(act.get("value", True))
        room.flags[flag] = value
        try:
            world_store.update_room_flags(player.world_id, room.id, {flag: value})
        except Exception:
            log.exception("failed to persist room flag %s", flag)
        return {"type": "flag_set", "flag": flag, "value": value}

    # ── Skill check resolver ──

    def _resolve_skill_check(self, player: AgentState, sc: dict) -> dict | None:
        from nachomud.rules.dice import roll_d20
        from nachomud.rules.stats import mod
        stat = str(sc.get("stat", "STR")).upper()
        if stat not in ("STR", "DEX", "CON", "INT", "WIS", "CHA"):
            return None
        try:
            dc = int(sc.get("dc", 10))
        except (TypeError, ValueError):
            dc = 10
        stat_mod = mod(player.stats.get(stat, 10))
        roll = roll_d20()
        total = roll + stat_mod
        success = total >= dc
        narration = (sc.get("on_success") if success else sc.get("on_fail")) or ""
        return {
            "stat": stat, "dc": dc, "roll": roll, "modifier": stat_mod,
            "total": total, "success": success, "narration": str(narration).strip(),
        }

    # ── World generation ──
    # Implementation lives in nachomud/ai/world_gen.py. The DM holds a
    # WorldGen instance and forwards generate_room() to it so callers can
    # keep using `dm.generate_room(...)` without knowing about the split.

    def generate_room(self, source: Room, direction: str, world_id: str,
                      *, requested_id: str | None = None,
                      max_retries: int = 2) -> Room:
        return self.world_gen.generate_room(
            source, direction, world_id,
            requested_id=requested_id, max_retries=max_retries,
        )


# ── Hint extraction ──

_HINT_RE = re.compile(r"(?im)^\s*HINT:\s*(.+?)\s*$")


def _extract_hint(text: str) -> tuple[str, str | None]:
    m = _HINT_RE.search(text)
    if not m:
        return text, None
    hint = m.group(1).strip()
    cleaned = (text[:m.start()] + text[m.end():]).strip()
    return cleaned, hint


def _build_adjudicate_prompt(player: AgentState, room: Room, action: str) -> str:
    from nachomud.rules.stats import mod
    stat_summary = ", ".join(f"{s} {player.stats.get(s, 10)} ({mod(player.stats.get(s, 10)):+d})"
                             for s in ("STR", "DEX", "CON", "INT", "WIS", "CHA"))
    parts = [
        f"Player: {player.name} the {player.race} {player.agent_class} (L{player.level}).",
        f"Stats: {stat_summary}.",
        f"HP {player.hp}/{player.max_hp}  MP {player.mp}/{player.max_mp}  "
        f"AP {player.ap}/{player.max_ap}  Gold {player.gold} gp.",
        f"Room: {room.name} — {room.description}",
    ]

    # Player's inventory — DM needs this to validate consume_item actions.
    if player.inventory:
        inv = ", ".join(it.name for it in player.inventory)
        parts.append(f"\nPlayer inventory (only items here can be consumed): {inv}")
    else:
        parts.append("\nPlayer inventory: empty.")

    # Equipment (so the DM doesn't have the player draw a sword they don't own)
    parts.append(
        f"Equipment: weapon={player.weapon.name}, armor={player.armor.name}, "
        f"ring={player.ring.name}."
    )

    # Mutable room flags — so the DM doesn't, e.g., 'open the door' after it's open
    if room.flags:
        flag_summary = ", ".join(f"{k}={v}" for k, v in room.flags.items())
        parts.append(f"Room flags: {flag_summary}")

    # Live presence — same grounding info the chat prompt gets
    presence = _presence_summary(player, room)
    if presence:
        parts.append("\nWho/what is present in this room RIGHT NOW (do not invent others):")
        parts.extend(f"  - {line}" for line in presence)
    else:
        parts.append("\nNo one else is here right now.")

    # Wares of any shopkeeper present, so the DM can answer "what does X sell?"
    # accurately and route the player to the right command.
    shop_lines = _wares_summary(player, room)
    if shop_lines:
        parts.append("\nWares for sale by present shopkeepers:")
        parts.extend(f"  - {line}" for line in shop_lines)

    parts.append(f"\nThe player wants to: {action}")
    parts.append("\nAdjudicate. Return only the JSON object.")
    return "\n".join(parts)


# ── Deterministic short-circuits ──
#
# When the player asks a factual question that the game engine already knows
# the answer to (what wares does X sell? how much for Y?), we answer from
# data instead of asking the LLM. This is the harmony point between the
# generative DM and the deterministic world: facts come from data, prose
# only over those facts.

_WARES_KEYWORDS = (
    "have for sale", "have to sell", "for sale", "what do you sell",
    "what does", "what's for sale", "what kind of", "what sort of",
    "wares", "stock", "carry", "got any", "selling", "got for sale",
    "what do you have", "what have you got",
)
_PRICE_KEYWORDS = ("how much", "price of", "what's the price", "cost of", "what does it cost")

# Self-status questions the player keeps asking the DM but which the engine
# can answer trivially from data.
_XP_KEYWORDS = ("xp", "experience", "exp")
_LEVEL_KEYWORDS = ("level up", "next level", "level", "leveling", "ding")
_GOLD_KEYWORDS = ("how much gold", "how much money", "what's my gold", "how much coin", "my gold")
_HP_KEYWORDS = ("how much hp", "what's my hp", "my health", "how much health")


def _try_deterministic_reply(player: AgentState, room: Room, message: str) -> str | None:
    """If the message asks a question we can answer from world data, return
    the canned answer. Otherwise return None and let the LLM handle it."""
    msg = (message or "").lower().strip()
    if not msg:
        return None

    # Self-status queries — answerable from the player object alone.
    if any(kw in msg for kw in _XP_KEYWORDS):
        from nachomud.characters.leveling import xp_to_next_level
        to_next = xp_to_next_level(player)
        if to_next > 100_000_000:
            return f"You have {player.xp} XP — and you're already at the cap."
        return (f"You have {player.xp} XP. {to_next} more to reach Level {player.level + 1}. "
                f"(Type `stats` to see the full sheet.)")
    if any(kw in msg for kw in _LEVEL_KEYWORDS):
        from nachomud.characters.leveling import xp_to_next_level
        to_next = xp_to_next_level(player)
        return (f"You're Level {player.level}. {to_next} XP until Level {player.level + 1}. "
                f"Slay enemies and complete deeds to earn it.")
    if any(kw in msg for kw in _GOLD_KEYWORDS):
        return f"You're carrying {player.gold} gp."
    if any(kw in msg for kw in _HP_KEYWORDS):
        return f"You're at {player.hp}/{player.max_hp} HP."

    from nachomud.world.routines import hour_from_minute, npcs_in_room
    hour = hour_from_minute((player.game_clock or {}).get("minute", 480))
    present = list(npcs_in_room(room.npcs, room.id, hour))
    shopkeepers = [(n, a) for n, a in present if n.wares]

    is_wares_query = any(kw in msg for kw in _WARES_KEYWORDS)
    is_price_query = any(kw in msg for kw in _PRICE_KEYWORDS)

    if is_wares_query and shopkeepers:
        # Find which shopkeeper they're asking about; default to all if ambiguous
        targeted = [n for n, _ in shopkeepers if _name_in_message(n.name, msg)]
        if not targeted:
            targeted = [n for n, _ in shopkeepers]
        out_lines = []
        for npc in targeted:
            items = ", ".join(f"{w['name']} — {w.get('price', 0)} gp" for w in npc.wares)
            first = npc.name.split()[0]
            out_lines.append(
                f"{npc.name} runs through her stock for you: {items}. "
                f"(Type `buy <item> from {first}` to purchase.)"
            )
        return "\n".join(out_lines)

    if is_price_query and shopkeepers:
        # Look for an item name in the message that matches any shopkeeper's wares
        for npc, _ in shopkeepers:
            for w in npc.wares:
                if w["name"].lower() in msg:
                    first = npc.name.split()[0]
                    return (f"{npc.name} eyes the {w['name']} and says: "
                            f"\"That'll be {w.get('price', 0)} gold.\" "
                            f"(`buy {w['name'].lower()} from {first}`)")
        # Mentioned a price but no item we recognize
        return None

    return None


def _name_in_message(name: str, msg: str) -> bool:
    name_l = name.lower()
    if name_l in msg:
        return True
    # First-name match (Greta, Marta, John, Bren)
    first = name_l.split()[0]
    return len(first) >= 3 and first in msg


def _wares_summary(player: AgentState, room: Room) -> list[str]:
    """Wares-for-sale listing from any shopkeeper present right now."""
    from nachomud.world.routines import hour_from_minute, npcs_in_room
    out: list[str] = []
    hour = hour_from_minute((player.game_clock or {}).get("minute", 480))
    for npc, _activity in npcs_in_room(room.npcs, room.id, hour):
        if not npc.wares:
            continue
        items = ", ".join(f"{w['name']} ({w.get('price', 0)} gp)" for w in npc.wares)
        out.append(f"{npc.name}: {items}")
    return out


