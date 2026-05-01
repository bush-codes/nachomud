"""Per-connection player session.

Routes WebSocket input to one of:
  - WelcomeHandler  (initial: load existing or create new)
  - CharCreator     (new character creation flow)
  - Game            (Phase 5+: command dispatch, exploration, DM chat)

The transport (server.py) feeds raw command text in, and the session emits
a list of (kind, payload) messages to send back.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field

import nachomud.characters.save as player_mod
import nachomud.world.starter as starter
from nachomud.characters.creation import CharCreator
from nachomud.style import _c, BOLD, CYAN, DIM, GREEN, MAGENTA, RED, YELLOW
from nachomud.ai.dm import DM, LLMFn
from nachomud.engine.game import Game
from nachomud.models import AgentState
from nachomud.ai.npc import NPCDialogue


# ── Boot banner ──

LOGO_LINES = [
    r"███╗   ██╗ █████╗  ██████╗██╗  ██╗ ██████╗ ███╗   ███╗██╗   ██╗██████╗",
    r"████╗  ██║██╔══██╗██╔════╝██║  ██║██╔═══██╗████╗ ████║██║   ██║██╔══██╗",
    r"██╔██╗ ██║███████║██║     ███████║██║   ██║██╔████╔██║██║   ██║██║  ██║",
    r"██║╚██╗██║██╔══██║██║     ██╔══██║██║   ██║██║╚██╔╝██║██║   ██║██║  ██║",
    r"██║ ╚████║██║  ██║╚██████╗██║  ██║╚██████╔╝██║ ╚═╝ ██║╚██████╔╝██████╔╝",
    r"╚═╝  ╚═══╝╚═╝  ╚═╝ ╚═════╝╚═╝  ╚═╝ ╚═════╝╚═╝     ╚═╝ ╚═════╝ ╚═════╝ ",
]

TAGLINES = [
    "Forge your saga.  Talk to the Dungeon Master.  Live forever.",
    "Every door opens onto procedural country.",
    "The world remembers what you killed.",
    "The Dungeon Master is always listening.",
    "Roll for initiative.  Hope for natural twenties.",
    "An LLM tells the story; the dice decide your fate.",
    "For explorers, talkers, and the kind of people who push every bookcase.",
    "Crit on 20.  Cry on 1.",
    "Walk past the watchtower.  See what the DM dreams up.",
    "Greta's apples are 2 gp.  Don't get any ideas.",
]


def _render_banner() -> str:
    out = [""]
    for line in LOGO_LINES:
        out.append(_c(line, BOLD + MAGENTA))
    out.append("")
    tagline = random.choice(TAGLINES)
    # Center the tagline under the logo (logo is ~73 chars wide)
    pad = max(0, (73 - len(tagline)) // 2)
    out.append(" " * pad + _c("⚔  ", DIM + CYAN) + _c(tagline, CYAN) + _c("  ⚔", DIM + CYAN))
    out.append("")
    return "\r\n".join(out) + "\r\n"

# ── Helpers ──

def _output(text: str) -> tuple[str, str]:
    return ("output", text)


def _prompt(text: str) -> tuple[str, str]:
    return ("prompt", text)


def _mode(name: str) -> tuple[str, str]:
    return ("mode", name)


def _status_for(agent: AgentState) -> dict:
    return {
        "type": "status",
        "hp": agent.hp, "max_hp": agent.max_hp,
        "mp": agent.mp, "max_mp": agent.max_mp,
        "ap": agent.ap, "max_ap": agent.max_ap,
        "ac": agent.ac, "level": agent.level, "xp": agent.xp,
    }


# ── In-game (Phase 5: real game loop) ──

def _ensure_starter_world(world_id: str) -> None:
    """Seed the Silverbrook starter town if not already present."""
    starter.seed_world(world_id, town="silverbrook")


# ── Welcome / save-pick ──

@dataclass
class WelcomeHandler:
    spawn_room: str = "silverbrook.inn"
    default_world_id: str = "default"
    # When set (browser anon UUID or signed-in account's player_id), the
    # welcome flow scopes to this one save instead of listing everyone's.
    anon_player_id: str = ""
    saves: list[dict] = field(default_factory=list)
    awaiting_save_pick: bool = False

    def start(self) -> list:
        msgs: list = [
            _mode("welcome"),
            _output(_render_banner()),
        ]
        if self.anon_player_id:
            return msgs + self._start_anon()
        # Legacy multi-save picker (curl / scripts without a pid)
        self.saves = player_mod.list_players()
        if self.saves:
            msgs.append(_output(f"{_c('Saved characters:', BOLD)}\r\n"))
            for i, s in enumerate(self.saves, 1):
                msgs.append(_output(f"  {i}) {s['name']} the {s['race']} {s['class']} (L{s['level']})\r\n"))
            msgs.append(_output(f"\r\nType a number to load, or {_c('n', BOLD)} to create a new character.\r\n"))
            self.awaiting_save_pick = True
        else:
            msgs.append(_output(f"No saved characters. Press {_c('ENTER', BOLD)} or type {_c('n', BOLD)} to create one.\r\n"))
            self.awaiting_save_pick = False
        msgs.append(_prompt(_c("> ", CYAN)))
        return msgs

    def _start_anon(self) -> list:
        """Anon flow: one save scoped to the browser/account UUID. If it
        exists, offer continue/restart; otherwise drop into char_create."""
        if player_mod.player_exists(self.anon_player_id):
            try:
                agent = player_mod.load_player(self.anon_player_id)
            except Exception:
                self.awaiting_save_pick = False
                return [_output(_c("Your save is corrupt — starting fresh.\r\n", RED)),
                        _prompt(_c("> ", CYAN))]
            self.saves = [{"player_id": self.anon_player_id,
                           "name": agent.name, "race": agent.race,
                           "class": agent.agent_class, "level": agent.level}]
            self.awaiting_save_pick = True
            return [
                _output(f"{_c('Welcome back,', BOLD)} {_c(agent.name, GREEN)} "
                        f"the {agent.race} {agent.agent_class} (L{agent.level}).\r\n"),
                _output(f"Press {_c('ENTER', BOLD)} to continue, or "
                        f"{_c('n', BOLD)} to abandon and roll a new character.\r\n"),
                _prompt(_c("> ", CYAN)),
            ]
        self.awaiting_save_pick = False
        return [
            _output(f"{_c('Welcome to NachoMUD.', BOLD)} Press {_c('ENTER', BOLD)} "
                    f"to create your character.\r\n"),
            _prompt(_c("> ", CYAN)),
        ]

    def handle(self, text: str) -> tuple[str, list, AgentState | None]:
        t = text.strip().lower()
        if self.anon_player_id and self.awaiting_save_pick:
            if t in ("", "y", "yes"):
                try:
                    agent = player_mod.load_player(self.anon_player_id)
                except Exception as e:
                    return ("stay",
                            [_output(_c(f"Failed to load: {e}\r\n", RED)), *self.start()[2:]],
                            None)
                return ("in_game",
                        [_output(_c(f"Loading {agent.name}...\r\n", GREEN))],
                        agent)
            if t in ("n", "new"):
                return ("char_create", [], None)
            return ("stay",
                    [_output(_c("Type ENTER to continue or 'n' for new.\r\n", RED)), *self.start()[2:]],
                    None)
        if self.anon_player_id:
            return ("char_create", [], None)
        if self.awaiting_save_pick:
            if t in ("n", "new", ""):
                return ("char_create", [], None)
            try:
                idx = int(t)
            except ValueError:
                return ("stay", [_output(_c("Pick a number or 'n'.\r\n", RED)), *self.start()[2:]], None)
            if not (1 <= idx <= len(self.saves)):
                return ("stay", [_output(_c(f"Pick 1-{len(self.saves)} or 'n'.\r\n", RED)), *self.start()[2:]], None)
            chosen = self.saves[idx - 1]
            try:
                agent = player_mod.load_player(chosen["player_id"])
            except Exception as e:
                return ("stay", [_output(_c(f"Failed to load: {e}\r\n", RED)), *self.start()[2:]], None)
            return ("in_game", [_output(_c(f"Loading {agent.name}...\r\n", GREEN))], agent)
        return ("char_create", [], None)


# ── Top-level session ──

@dataclass
class Session:
    spawn_room: str = "silverbrook.inn"
    default_world_id: str = "default"
    dm_llm: LLMFn | None = None  # for tests to inject a stub DM
    npc_llm: LLMFn | None = None
    npc_summarizer: LLMFn | None = None
    mob_decider: object | None = None  # for tests to inject deterministic mob AI

    # Optional WorldLoop. When set, in-game commands route through the
    # loop's serialization lock so this human shares the world with the
    # 4 AI agents. When None (test mode / standalone), drives a private
    # Game directly.
    world_loop: object | None = None

    # Anon UUID from the browser's localStorage OR the signed-in account's
    # primary_player_id. When set, welcome flow scopes to this one save
    # and char_create assigns it as the new character's player_id.
    anon_player_id: str = ""

    handler_kind: str = "welcome"
    welcome: WelcomeHandler = field(default_factory=WelcomeHandler)
    creator: CharCreator | None = None
    game: Game | None = None
    agent: AgentState | None = None
    actor_id: str = ""

    def start(self) -> list:
        self.welcome = WelcomeHandler(
            spawn_room=self.spawn_room,
            default_world_id=self.default_world_id,
            anon_player_id=self.anon_player_id,
        )
        return self.welcome.start()

    def handle(self, text: str) -> list:
        if self.handler_kind == "welcome":
            next_kind, msgs, agent = self.welcome.handle(text)
            if next_kind == "char_create":
                return msgs + self._enter_char_create()
            if next_kind == "in_game":
                self.agent = agent
                return msgs + self._enter_in_game(agent)
            return msgs

        if self.handler_kind == "char_create":
            assert self.creator is not None
            msgs = self.creator.handle_input(text)
            if self.creator.is_complete():
                agent = self.creator.build_agent()
                # Bind the new character to the browser anon UUID / account
                # primary_player_id so the next visit reloads it.
                if self.anon_player_id:
                    agent.player_id = self.anon_player_id
                self.agent = agent
                return msgs + self._enter_in_game(agent)
            return msgs

        if self.handler_kind == "in_game":
            assert self.game is not None
            # World-loop path: route through the loop's serialization lock
            # so commands serialize against agent ticks and other actors.
            # Loop also broadcasts msgs to subscribers, so we return [].
            if self.world_loop is not None and self.actor_id:
                self.world_loop.submit_command(self.actor_id, text)
                return []
            return self.game.handle(text)

        return [_output(_c(f"Internal error: unknown handler {self.handler_kind}\r\n", RED))]

    # ── Transitions ──

    def _enter_char_create(self) -> list:
        self.handler_kind = "char_create"
        self.creator = CharCreator(default_world_id=self.default_world_id, spawn_room=self.spawn_room)
        return [_mode("char_create"), *self.creator.start()]

    def _enter_in_game(self, agent: AgentState) -> list:
        import nachomud.world.store as ws_mod
        self.handler_kind = "in_game"
        _ensure_starter_world(agent.world_id)
        if not agent.room_id:
            agent.room_id = self.spawn_room
        if not agent.respawn_room:
            agent.respawn_room = self.spawn_room
        # Rescue stranded actors (room deleted between sessions)
        rescue = False
        if not ws_mod.room_exists(agent.world_id, agent.room_id):
            rescue = True
        msgs_pre: list = []
        if rescue:
            agent.room_id = self.spawn_room
            msgs_pre.append(_output(
                _c("(Your last location is no longer in the world. "
                   f"You find yourself back at {self.spawn_room}.)\r\n", YELLOW)
            ))
        player_mod.save_player(agent)
        # World-loop path: register with the WorldLoop, share its Game.
        if self.world_loop is not None:
            actor = self.world_loop.register_human(agent)
            self.actor_id = actor.actor_id
            self.game = actor.game
            return msgs_pre + self.world_loop.start_actor(self.actor_id)
        # Legacy fallback (tests / standalone): private Game per session.
        self.game = Game(
            player=agent,
            dm=DM(llm=self.dm_llm),
            npc_dialogue=NPCDialogue(llm=self.npc_llm, summarizer=self.npc_summarizer),
            mob_decider=self.mob_decider,  # type: ignore[arg-type]
        )
        return msgs_pre + self.game.start()
