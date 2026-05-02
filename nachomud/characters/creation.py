"""Character creation state machine.

Drives the player through: name → race → class → point-buy → confirm → spawn.
Pure state machine — no I/O. The server feeds it text input and gets back a
list of (kind, payload) messages to send to the client.

Usage:
    cc = CharCreator(default_world_id="default", spawn_room="silverbrook.inn")
    msgs = cc.start()                  # initial prompts
    msgs = cc.handle_input("Aric")     # advance the state machine
    ...
    if cc.is_complete():
        agent = cc.build_agent()       # AgentState ready to save + play
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from urllib.parse import urlparse

from nachomud.characters.character import (
    create_character,
    class_attack_bonus,
    class_damage_mod,
    spell_save_dc,
)
from nachomud.rules.classes import CLASS_DEFINITIONS
from nachomud.rules.races import RACE_DEFINITIONS
from nachomud.models import AgentState
from nachomud.rules.stats import (
    POINT_BUY_BUDGET,
    POINT_BUY_COSTS,
    POINT_BUY_MAX,
    POINT_BUY_MIN,
    STAT_NAMES,
    Stats,
    mod,
    validate_point_buy,
)

from nachomud.style import BOLD, CYAN, DIM, GREEN, MAGENTA, RED, RESET, YELLOW, _c


# ── State machine ──

STATES = ("name", "race", "class", "point_buy", "dm_url", "confirm", "done")


@dataclass
class CharCreator:
    default_world_id: str = "default"
    spawn_room: str = "silverbrook.inn"

    # Inputs collected
    state: str = "name"
    name: str = ""
    race: str = ""
    class_name: str = ""
    stats: Stats = field(default_factory=Stats)
    current_stat_idx: int = 0  # which stat we're filling in point_buy mode
    dm_ollama_url: str = ""    # per-character DM-tier Ollama (tailnet URL)

    def is_complete(self) -> bool:
        return self.state == "done"

    # ── Public API: returns list of (kind, payload) messages ──

    def start(self) -> list[tuple[str, str]]:
        msgs: list[tuple[str, str]] = []
        msgs.append(("output",
                     f"{_c('=== Character Creation ===', BOLD + CYAN)}\r\n\r\n"
                     f"You will pick a name, race, and class, then assign six ability "
                     f"scores via point-buy.\r\n\r\n"))
        msgs.extend(self._prompt_for_state())
        return msgs

    def handle_input(self, text: str) -> list[tuple[str, str]]:
        text = text.strip()
        if not text:
            return self._prompt_for_state()

        if text.lower() == "restart":
            self.state = "name"
            self.name = ""
            self.race = ""
            self.class_name = ""
            self.stats = Stats()
            self.current_stat_idx = 0
            self.dm_ollama_url = ""
            return [("output", _c("Restarting character creation.\r\n", YELLOW)), *self._prompt_for_state()]

        try:
            handler = getattr(self, f"_handle_{self.state}")
        except AttributeError:
            return [("output", _c(f"Internal error: unknown state {self.state}\r\n", RED))]
        return handler(text)

    # ── State handlers ──

    def _handle_name(self, text: str) -> list[tuple[str, str]]:
        if len(text) > 24:
            return [("output", _c("Name too long (max 24 chars). Try again.\r\n", RED)), *self._prompt_for_state()]
        if not text.replace(" ", "").replace("'", "").replace("-", "").isalnum():
            return [("output", _c("Letters, spaces, hyphens, and apostrophes only. Try again.\r\n", RED)), *self._prompt_for_state()]
        self.name = text
        self.state = "race"
        return [("output", _c(f"Welcome, {self.name}.\r\n\r\n", GREEN)), *self._prompt_for_state()]

    def _handle_race(self, text: str) -> list[tuple[str, str]]:
        race = self._resolve_choice(text, list(RACE_DEFINITIONS.keys()))
        if race is None:
            return [("output", _c("Pick a number 1-5 or type the race name.\r\n", RED)), *self._prompt_for_state()]
        self.race = race
        self.state = "class"
        rdef = RACE_DEFINITIONS[race]
        mods = ", ".join(f"+{v} {k}" for k, v in rdef["stat_mods"].items())
        return [("output", f"{_c(race, BOLD)} chosen ({mods}). Trait: {rdef['trait']}.\r\n\r\n"), *self._prompt_for_state()]

    def _handle_class(self, text: str) -> list[tuple[str, str]]:
        cls = self._resolve_choice(text, list(CLASS_DEFINITIONS.keys()))
        if cls is None:
            return [("output", _c("Pick a number 1-6 or type the class name.\r\n", RED)), *self._prompt_for_state()]
        self.class_name = cls
        # Initialize stats to base 8s
        self.stats = Stats(STR=8, DEX=8, CON=8, INT=8, WIS=8, CHA=8)
        self.current_stat_idx = 0
        self.state = "point_buy"
        cdef = CLASS_DEFINITIONS[cls]
        return [("output", f"{_c(cls, BOLD)} chosen. Hit die d{cdef['hit_die']}, primary stat " f"{cdef['primary_stat']}, save proficiencies " f"{', '.join(cdef['save_proficiencies'])}.\r\n\r\n" f"{_c('Point-buy:', BOLD)} you have {POINT_BUY_BUDGET} points. " f"Each stat starts at 8 (free) and goes up to 15.\r\n" f"  Costs: 9=1, 10=2, 11=3, 12=4, 13=5, 14=7, 15=9\r\n" f"  (You can type 'standard' to use the standard array 15,14,13,12,10,8.)\r\n\r\n"), *self._prompt_for_state()]

    def _handle_point_buy(self, text: str) -> list[tuple[str, str]]:
        if text.lower() == "standard":
            cdef = CLASS_DEFINITIONS[self.class_name]
            primary = cdef["primary_stat"]
            order_pref = [primary] + [s for s in STAT_NAMES if s != primary]
            values = [15, 14, 13, 12, 10, 8]
            for stat, v in zip(order_pref, values, strict=False):
                self.stats.set(stat, v)
            self.current_stat_idx = len(STAT_NAMES)
            self.state = "dm_url"
            return [("output", _c("Standard array assigned (primary stat first).\r\n", GREEN)), *self._prompt_for_state()]

        if self.current_stat_idx >= len(STAT_NAMES):
            return self._prompt_for_state()

        stat_name = STAT_NAMES[self.current_stat_idx]
        try:
            value = int(text)
        except ValueError:
            return [("output", _c(f"Type a number between {POINT_BUY_MIN} and {POINT_BUY_MAX}.\r\n", RED)), *self._prompt_for_state()]

        if value < POINT_BUY_MIN or value > POINT_BUY_MAX:
            return [("output", _c(f"{stat_name} must be {POINT_BUY_MIN}-{POINT_BUY_MAX}.\r\n", RED)), *self._prompt_for_state()]

        # Tentatively set, verify budget across whatever's set so far
        prev = self.stats.get(stat_name)
        self.stats.set(stat_name, value)
        # Compute cost of finalized stats only
        committed = {STAT_NAMES[i]: self.stats.get(STAT_NAMES[i]) for i in range(self.current_stat_idx + 1)}
        spent = sum(POINT_BUY_COSTS[v] for v in committed.values())
        if spent > POINT_BUY_BUDGET:
            self.stats.set(stat_name, prev)
            remaining = POINT_BUY_BUDGET - sum(POINT_BUY_COSTS[committed[STAT_NAMES[i]]] for i in range(self.current_stat_idx))
            return [("output", _c(f"That overspends the budget. {remaining} points left for {stat_name}.\r\n", RED)), *self._prompt_for_state()]

        self.current_stat_idx += 1
        if self.current_stat_idx >= len(STAT_NAMES):
            self.state = "dm_url"
        return self._prompt_for_state()

    def _handle_dm_url(self, text: str) -> list[tuple[str, str]]:
        err = _validate_dm_ollama_url(text)
        if err is not None:
            return [("output", _c(err + "\r\n", RED)), *self._prompt_for_state()]
        self.dm_ollama_url = text.strip()
        self.state = "confirm"
        return [("output", _c(f"DM Ollama set to {self.dm_ollama_url}.\r\n\r\n", GREEN)),
                *self._prompt_for_state()]

    def _handle_confirm(self, text: str) -> list[tuple[str, str]]:
        t = text.lower()
        if t in ("y", "yes", "confirm"):
            self.state = "done"
            return [("output", _c("Character created. Stepping into the world...\r\n\r\n", GREEN))]
        if t in ("n", "no", "redo"):
            self.state = "name"
            self.name = ""
            self.race = ""
            self.class_name = ""
            self.stats = Stats()
            self.current_stat_idx = 0
            self.dm_ollama_url = ""
            return [("output", _c("Starting over.\r\n\r\n", YELLOW)), *self._prompt_for_state()]
        return [("output", _c("Type y to confirm, n to start over, or 'restart' anytime.\r\n", RED)), *self._prompt_for_state()]

    # ── Prompt rendering ──

    def _prompt_for_state(self) -> list[tuple[str, str]]:
        if self.state == "name":
            return [("output", "Enter your character's name: "),
                    ("prompt", _c("name> ", CYAN))]
        if self.state == "race":
            lines = [_c("Choose a race:", BOLD)]
            for i, (rname, rdef) in enumerate(RACE_DEFINITIONS.items(), 1):
                mods = ", ".join(f"+{v} {k}" for k, v in rdef["stat_mods"].items())
                lines.append(f"  {i}) {_c(rname, BOLD)} — {mods}. {_c(rdef['trait'], DIM)}")
            return [("output", "\r\n".join(lines) + "\r\n"),
                    ("prompt", _c("race> ", CYAN))]
        if self.state == "class":
            lines = [_c("Choose a class:", BOLD)]
            for i, (cname, cdef) in enumerate(CLASS_DEFINITIONS.items(), 1):
                lines.append(
                    f"  {i}) {_c(cname, BOLD)} — d{cdef['hit_die']} HD, primary "
                    f"{cdef['primary_stat']}, abilities: {', '.join(cdef['starting_abilities'])} "
                    f"(more at L3/5/7)"
                )
            return [("output", "\r\n".join(lines) + "\r\n"),
                    ("prompt", _c("class> ", CYAN))]
        if self.state == "point_buy":
            lines = []
            assigned = [(STAT_NAMES[i], self.stats.get(STAT_NAMES[i])) for i in range(self.current_stat_idx)]
            spent = sum(POINT_BUY_COSTS[v] for _, v in assigned)
            remaining = POINT_BUY_BUDGET - spent
            if assigned:
                row = "  ".join(f"{n}={v}" for n, v in assigned)
                lines.append(_c(f"Assigned so far: {row}", DIM))
                lines.append(_c(f"Points spent: {spent}/{POINT_BUY_BUDGET}  ({remaining} remaining)", DIM))
            stat = STAT_NAMES[self.current_stat_idx]
            lines.append(f"Set {_c(stat, BOLD)} (8-15): ")
            return [("output", "\r\n".join(lines)),
                    ("prompt", _c(f"{stat}> ", CYAN))]
        if self.state == "dm_url":
            lines = [
                _c("=== DM Ollama URL ===", BOLD + CYAN),
                "",
                "Each character runs the Dungeon Master on their own GPU,",
                "reachable over Tailscale. On your machine:",
                "  1) Install Tailscale and share your node into the operator's tailnet",
                "  2) Run Ollama with " + _c("OLLAMA_HOST=0.0.0.0", BOLD)
                + " bound (so the tailnet can reach it)",
                "  3) Pull the smart-tier model: " + _c("ollama pull llama3.1:8b-instruct-q4_K_M", BOLD),
                "  4) Find your tailnet IP with " + _c("tailscale ip -4", BOLD),
                "",
                _c("Paste the full URL (e.g. http://100.64.1.5:11434):", DIM),
            ]
            return [("output", "\r\n".join(lines) + "\r\n"),
                    ("prompt", _c("dm-url> ", CYAN))]
        if self.state == "confirm":
            preview = self._build_preview_agent()
            cdef = CLASS_DEFINITIONS[self.class_name]
            rdef = RACE_DEFINITIONS[self.race]
            lines = [
                "",
                _c("=== Confirm character ===", BOLD + CYAN),
                f"{_c(preview.name, BOLD)} the {preview.race} {preview.agent_class}",
                _c(f"  Race trait: {rdef['trait_description']}", DIM),
                "",
                "Final stats (after racial mods):",
            ]
            for s in STAT_NAMES:
                v = preview.stats[s]
                m = mod(v)
                sign = "+" if m >= 0 else ""
                lines.append(f"  {_c(s, BOLD)} {v}  ({sign}{m})")
            lines.extend([
                "",
                f"  HP {preview.hp}/{preview.max_hp}   AC {preview.ac}   "
                f"Speed {preview.speed}   Prof +{preview.proficiency_bonus}",
                f"  Attack: +{class_attack_bonus(preview)} to hit, "
                f"{preview.weapon.damage_die}+{class_damage_mod(preview)} damage  ({preview.weapon.name})",
            ])
            if cdef.get("caster_mod"):
                lines.append(f"  Spell save DC: {spell_save_dc(preview)}")
            lines.extend([
                f"  Resource: {(preview.max_ap and f'AP {preview.ap}/{preview.max_ap}') or f'MP {preview.mp}/{preview.max_mp}'}",
                f"  Abilities: {', '.join(preview.abilities)}",
                f"  Saves proficient in: {', '.join(preview.save_proficiencies)}",
                f"  DM Ollama: {self.dm_ollama_url}",
                "",
                "Confirm? (y/n)",
            ])
            return [("output", "\r\n".join(lines) + "\r\n"),
                    ("prompt", _c("confirm> ", CYAN))]
        if self.state == "done":
            return []
        return []

    # ── Helpers ──

    def _resolve_choice(self, text: str, options: list[str]) -> str | None:
        # Numeric pick
        try:
            n = int(text)
            if 1 <= n <= len(options):
                return options[n - 1]
        except ValueError:
            pass
        # Name match (case-insensitive, prefix)
        t = text.lower()
        for opt in options:
            if opt.lower() == t:
                return opt
        for opt in options:
            if opt.lower().startswith(t):
                return opt
        return None

    def _build_preview_agent(self) -> AgentState:
        return create_character(
            name=self.name,
            race=self.race,
            class_name=self.class_name,
            base_stats=self.stats,
            level=1,
            player_id=str(uuid.uuid4()),
            respawn_room=self.spawn_room,
            world_id=self.default_world_id,
        )

    def build_agent(self, *, player_id: str | None = None) -> AgentState:
        """Build the final AgentState. Caller is responsible for save_player()."""
        if not self.is_complete():
            raise RuntimeError(f"CharCreator not yet complete (state={self.state})")
        ok, reason = validate_point_buy(self.stats)
        if not ok:
            raise ValueError(f"point-buy invalid: {reason}")
        a = create_character(
            name=self.name,
            race=self.race,
            class_name=self.class_name,
            base_stats=self.stats,
            level=1,
            player_id=player_id or str(uuid.uuid4()),
            respawn_room=self.spawn_room,
            world_id=self.default_world_id,
        )
        a.room_id = self.spawn_room
        a.dm_ollama_url = self.dm_ollama_url
        return a


# ── Validation helpers ──

def _validate_dm_ollama_url(text: str) -> str | None:
    """Return error message or None if URL is acceptable. Required:
    http(s) scheme, hostname present. Port is recommended but not
    required (caller will discover the wrong port the first time the
    DM tries to talk and the player will get the in-world fallback)."""
    raw = text.strip()
    if not raw:
        return "URL can't be empty. Paste a tailnet URL like http://100.64.1.5:11434."
    try:
        parsed = urlparse(raw)
    except ValueError:
        return "Couldn't parse that URL. Try http://100.64.1.5:11434."
    if parsed.scheme not in ("http", "https"):
        return "URL must start with http:// or https://"
    if not parsed.hostname:
        return "URL is missing a host. Try http://100.64.1.5:11434."
    return None
