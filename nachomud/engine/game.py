"""Player-mode game loop: command dispatch, exploration, inventory, sleep,
DM fall-through. Combat is plugged in during Phase 7 — for now fighting
is not yet wired (but `attack` echoes a placeholder).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from collections.abc import Callable

import nachomud.characters.save as player_mod
import nachomud.world.store as world_store
from nachomud.ai.dm import DM
from nachomud.ai.npc import NPCDialogue
from nachomud.combat.encounter import Encounter, MobDecider
from nachomud.models import AgentState, Item, Room
from nachomud.style import BOLD, CYAN, DIM, GREEN, MAGENTA, RED, YELLOW, _c
from nachomud.world.directions import LONG_TO_SHORT
from nachomud.world.routines import hour_from_minute, npcs_in_room
import contextlib


# ── ANSI helpers (re-export) ──

def _output(text: str) -> tuple[str, str]:
    return ("output", text)


def _prompt(text: str) -> tuple[str, str]:
    return ("prompt", text)


def _mode(name: str) -> tuple[str, str]:
    return ("mode", name)


def _status(p: AgentState) -> dict:
    return {
        "type": "status",
        "hp": p.hp, "max_hp": p.max_hp,
        "mp": p.mp, "max_mp": p.max_mp,
        "ap": p.ap, "max_ap": p.max_ap,
        "ac": p.ac, "level": p.level, "xp": p.xp,
    }


# ── Direction aliases ──

_DIRS = {
    "n": "north", "north": "north",
    "s": "south", "south": "south",
    "e": "east",  "east": "east",
    "w": "west",  "west": "west",
    "u": "up",    "up":   "up",
    "d": "down",  "down": "down",
}

# Commands that take no arguments — if the user types them with extra text,
# we route the whole input to the DM instead (so "i pushed the bookcase"
# doesn't get parsed as `i` = inventory).
_NO_ARG_COMMANDS = {
    "i", "inv", "inventory",
    "stats",
    "who",
    "help",
    "save",
    "quit", "exit",
    "exits",
}

# `attack <mob>` is the explicit canonical fast-path command.
# Natural attack verbs ("punch glimmerfang", "stab the goblin") fall through
# to the DM, which decides whether the action triggers combat by emitting
# an `engage_combat` action — same pattern as `consume_item`/`set_flag`.
_ATTACK_FAST_PATH = {"attack"}


# ── Game-clock cost per command (in game minutes) ──

# ── Shared helpers (used by both fast-path commands and DM actions) ──

_CONNECTOR_PREFIXES = ("about ", "that ", "regarding ", "concerning ", "of ",
                       "if ", "whether ", "where ", "what ", "why ", "how ",
                       "who ", "when ")

# Words that appear in NPC names but aren't distinctive enough for
# first-word matching. "Old John" / "Old Marta" share "Old"; only the
# distinctive part should match in the fallback.
_NAME_TITLES = {"old", "captain", "sir", "lord", "lady", "mr", "ms", "mrs",
                "master", "mistress", "elder", "young", "the"}


def _distinctive_name_parts(name: str) -> list[str]:
    """Return the non-title words of an NPC name."""
    parts = name.lower().split()
    distinctive = [p for p in parts if p not in _NAME_TITLES]
    return distinctive or parts  # if everything is a title, fall back to all parts


def _strip_connector(text: str) -> str:
    """Strip a leading 'about ', 'that ', etc. from the message after the NPC
    name, so 'Marta about her food' yields message 'her food'."""
    t = text.strip()
    low = t.lower()
    for prefix in _CONNECTOR_PREFIXES:
        if low.startswith(prefix):
            # Keep question words; only consume pure connectors
            if prefix in ("about ", "that ", "regarding ", "concerning ", "of "):
                t = t[len(prefix):].strip()
            break
    return t



def _equip_from_inventory(player, query: str) -> dict:
    """Find an inventory item matching `query`, swap it into the appropriate
    slot, and return {ok, message, slot, item_name}. Recomputes AC if armor
    or shield changed. Validates class restrictions."""
    from nachomud.rules.stats import compute_ac, mod
    q = query.strip().lower()
    if not q:
        return {"ok": False, "message": "Equip what?"}
    target = next((it for it in player.inventory if q in it.name.lower()), None)
    if target is None:
        return {"ok": False, "message": f"You aren't carrying anything matching '{query}'."}
    slot = (target.slot or "").lower()
    if slot not in {"weapon", "armor", "ring", "shield"}:
        return {"ok": False, "message": f"{target.name} isn't equippable (slot={slot or 'none'})."}
    # Class restriction
    if target.allowed_classes and player.agent_class not in target.allowed_classes:
        return {"ok": False,
                "message": f"{target.name} can only be used by: {', '.join(target.allowed_classes)}."}
    # Swap
    old = getattr(player, slot, None)
    if old is not None and old.name and old.name.lower() != "unarmed" and \
       old.name.lower() != "clothes" and old.name.lower() != "plain ring":
        # Move the previously-equipped item into inventory
        player.inventory.append(old)
    setattr(player, slot, target)
    player.inventory.remove(target)
    # Recompute AC if armor/shield changed
    if slot in ("armor", "shield"):
        dex_mod = mod(player.stats.get("DEX", 10))
        armor = player.armor
        shield = player.shield
        player.ac = compute_ac(
            dex_modifier=dex_mod,
            armor_base=(armor.armor_base or 10),
            armor_max_dex=armor.armor_max_dex,
            shield_bonus=(shield.shield_bonus if shield else 0),
            misc_bonus=(player.ring.ac_bonus if player.ring else 0),
        )
    return {"ok": True, "message": f"You equip the {target.name}.",
            "slot": slot, "item_name": target.name}


CLOCK_COSTS = {
    "look": 5,
    "look_at": 2,
    "move": 1,
    "talk": 5,
    "tell": 5,
    "ask": 5,
    "dm": 5,
    "inventory": 0,
    "stats": 0,
    "who": 0,
    "help": 0,
    "save": 0,
    "quit": 0,
    "get": 1,
    "drop": 1,
    "buy": 2,
    "wares": 1,
    "wait": None,  # variable
    "sleep": None,  # variable
    "default": 5,
}


def advance_clock(p: AgentState, minutes: int) -> None:
    if not p.game_clock:
        p.game_clock = {"day": 1, "minute": 480}
    p.game_clock["minute"] = p.game_clock.get("minute", 480) + minutes
    while p.game_clock["minute"] >= 1440:
        p.game_clock["minute"] -= 1440
        p.game_clock["day"] = p.game_clock.get("day", 1) + 1


def clock_str(p: AgentState) -> str:
    g = p.game_clock or {"day": 1, "minute": 480}
    h = (g["minute"] // 60) % 24
    m = g["minute"] % 60
    return f"day {g['day']} {h:02d}:{m:02d}"


# ── Sensory rendering ──

def render_room(p: AgentState, room: Room,
                *, co_residents: list[str] | None = None) -> str:
    hour = hour_from_minute(p.game_clock.get("minute", 480))
    lines = []
    lines.append(_c(room.name, BOLD + CYAN))
    lines.append(room.description)
    # NPCs present right now (filtered by routines)
    npc_pairs = npcs_in_room(room.npcs, room.id, hour)
    if npc_pairs:
        lines.append("")
        lines.append(_c("People here:", BOLD))
        for npc, activity in npc_pairs:
            extra = f" ({_c(activity, DIM)})" if activity else ""
            lines.append(f"  {_c(npc.name, MAGENTA)} — {npc.title}{extra}")
    # Other actors (humans + agents) sharing this room
    if co_residents:
        lines.append("")
        lines.append(_c("Adventurers here:", BOLD))
        for name in co_residents:
            lines.append(f"  {_c(name, GREEN)}")
    # Mobs in this room (live)
    mobs = world_store.mobs_in_room(p.world_id, room.id, alive_only=True)
    if mobs:
        lines.append("")
        lines.append(_c("Also here:", BOLD))
        for m in mobs:
            lines.append(f"  {_c(m.name, RED)} (HP {m.hp}/{m.max_hp})")
    # Items in this room
    items = world_store.items_in_room(p.world_id, room.id)
    if items:
        lines.append("")
        lines.append(_c("On the ground:", BOLD))
        for i in items:
            lines.append(f"  {_c(i.get('name', '?'), YELLOW)}")
    # Exits
    if room.exits:
        lines.append("")
        lines.append(_c("Exits:", BOLD) + " " + ", ".join(sorted(room.exits.keys())))
    return "\r\n".join(lines) + "\r\n"


# ── Game loop ──

@dataclass
class Game:
    player: AgentState
    dm: DM = field(default_factory=DM)
    npc_dialogue: NPCDialogue = field(default_factory=NPCDialogue)
    mob_decider: MobDecider | None = None
    show_clock: bool = True
    # Returns display names of OTHER actors currently in the same room
    # as `room_id`. Wired by WorldLoop; None for tests / standalone Game
    # (in which case "Adventurers here:" never renders).
    co_residents_fn: Callable[[str], list[str]] | None = None

    # Snapshot of the current room (loaded lazily)
    _room: Room | None = None
    _encounter: Encounter | None = None
    _pending_witness: list[str] = field(default_factory=list)

    def _co_residents(self) -> list[str]:
        if self.co_residents_fn is None or not self.player.room_id:
            return []
        try:
            return self.co_residents_fn(self.player.room_id)
        except Exception:
            return []

    def start(self) -> list:
        self._load_room()
        msgs: list = [
            _mode("explore"),
            _output(_c(f"\r\nYou stand in {self._room.name}.\r\n", BOLD + GREEN)),
            _output(render_room(self.player, self._room, co_residents=self._co_residents())),
            _status(self.player),
            self._make_prompt(),
        ]
        return msgs

    def handle(self, text: str) -> list:
        text = text.strip()
        if not text:
            return [self._make_prompt()]

        # Combat takes precedence — all input goes through the encounter.
        if self._encounter is not None and self._encounter.is_active():
            msgs = self._encounter.handle_player_input(text)
            return self._maybe_finish_combat(msgs)

        cmd, _, arg = text.partition(" ")
        cmd_lower = cmd.lower()
        arg = arg.strip()

        # Direction shortcut: "n", "north", etc.
        if cmd_lower in _DIRS and not arg:
            return self._cmd_move(_DIRS[cmd_lower])
        # Two-word direction: "go north"
        if cmd_lower == "go" and arg.lower() in _DIRS:
            return self._cmd_move(_DIRS[arg.lower()])

        # Fast path: `attack <mob>` enters combat mode immediately.
        # Other attack-flavored verbs ("punch <mob>") fall through to the DM,
        # which can emit an `engage_combat` action to start combat (with
        # narration in the player's preferred phrasing).
        if cmd_lower in _ATTACK_FAST_PATH and arg:
            return self._cmd_attack(arg)

        # No-arg commands that should fall through to DM if invoked with an argument
        # (so "I push the bookcase" doesn't get parsed as `i` = inventory).
        if cmd_lower in _NO_ARG_COMMANDS and arg:
            return self._cmd_adjudicate(text)

        handler = self._dispatch(cmd_lower)
        if handler is None:
            # Free-form action: route to DM adjudication (skill check, hint, narrate)
            result = self._cmd_adjudicate(text)
        else:
            result = handler(arg)
        return self._inject_witness(result)

    def _inject_witness(self, result: list) -> list:
        """Insert any pending mob witness messages just before the trailing prompt."""
        if not self._pending_witness:
            return result
        witness_msgs = self._drain_witness()
        if result and isinstance(result[-1], tuple) and result[-1][0] == "prompt":
            return result[:-1] + witness_msgs + [result[-1]]
        return result + witness_msgs

    # ── Dispatch table ──

    def _dispatch(self, cmd: str) -> Callable[[str], list] | None:
        return {
            "look": self._cmd_look,
            "l":    self._cmd_look,
            "map":  self._cmd_map,
            "exits": self._cmd_exits,
            "inventory": self._cmd_inventory,
            "inv": self._cmd_inventory,
            "i":   self._cmd_inventory,
            "stats": self._cmd_stats,
            "who": self._cmd_who,
            "help": self._cmd_help,
            "save": self._cmd_save,
            "quit": self._cmd_quit,
            "exit": self._cmd_quit,
            "get": self._cmd_get,
            "take": self._cmd_get,
            "drop": self._cmd_drop,
            "sleep": self._cmd_sleep,
            "rest": self._cmd_sleep,
            "wait": self._cmd_wait,
            "dm":   self._cmd_dm,
            "ask":  self._cmd_dm,
            "talk": self._cmd_talk,
            "tell": self._cmd_tell,
            "wares": self._cmd_wares,
            "shop": self._cmd_wares,
            "buy":  self._cmd_buy,
            "equip": self._cmd_equip,
            "wield": self._cmd_equip,
            "wear":  self._cmd_equip,
        }.get(cmd)

    # ── Helpers ──

    def _load_room(self) -> Room:
        if self._room is None or self._room.id != self.player.room_id:
            self._room = world_store.load_room(self.player.world_id, self.player.room_id)
        return self._room

    def _make_prompt(self) -> tuple[str, str]:
        p = self.player
        clock = clock_str(p) if self.show_clock else ""
        bar = f"HP {p.hp}/{p.max_hp}"
        if p.max_mp:
            bar += f" MP {p.mp}/{p.max_mp}"
        if p.max_ap:
            bar += f" AP {p.ap}/{p.max_ap}"
        bar += f" {p.gold}gp"
        prefix = _c(f"[{bar}] ", DIM)
        if clock:
            prefix = _c(f"[{clock}] ", DIM) + prefix
        return _prompt(prefix + _c(f"{p.name}> ", GREEN))

    def _advance(self, key: str, minutes: int | None = None) -> None:
        """Advance this actor's game clock. Mob ticking is driven globally
        by the WorldLoop; witness lines for this actor's room arrive via
        queue_witness()."""
        cost = minutes if minutes is not None else CLOCK_COSTS.get(key, CLOCK_COSTS["default"])
        if not cost:
            return
        advance_clock(self.player, cost)

    def queue_witness(self, lines: list[str]) -> None:
        """Push witness lines onto this actor's pending queue. Called by
        WorldLoop during the global mob tick."""
        for line in lines:
            self._pending_witness.append(line)

    def _drain_witness(self) -> list:
        if not self._pending_witness:
            return []
        text = "\r\n".join(self._pending_witness) + "\r\n"
        self._pending_witness = []
        return [_output(_c(text, DIM))]

    def _persist(self) -> None:
        with contextlib.suppress(Exception):
            player_mod.save_player(self.player)

    # ── Commands ──

    def _cmd_look(self, arg: str) -> list:
        room = self._load_room()
        if not arg:
            self._advance("look")
            return [_output(render_room(self.player, room, co_residents=self._co_residents())), self._make_prompt()]
        # look at <thing> — let DM narrate
        return self._cmd_dm(f"look at {arg}")  # chat-style is right for examining

    def _cmd_exits(self, arg: str) -> list:
        room = self._load_room()
        if not room.exits:
            return [_output(_c("No visible exits.\r\n", DIM)), self._make_prompt()]
        return [_output(_c("Exits: ", BOLD) + ", ".join(sorted(room.exits.keys())) + "\r\n"),
                self._make_prompt()]

    def _cmd_move(self, direction: str) -> list:
        room = self._load_room()
        dest = room.exits.get(direction)
        # Allow short/long forms in room data: try both
        if not dest:
            dest = room.exits.get(LONG_TO_SHORT.get(direction, direction))
        if not dest:
            return [_output(_c(f"You cannot go {direction} from here.\r\n", RED)), self._make_prompt()]

        gen_msg = ""
        if not world_store.room_exists(self.player.world_id, dest):
            # Trigger DM-driven generation. Use the placeholder ID as the new room ID
            # so the source room's existing exit pointer remains valid.
            from nachomud.ai.llm import LLMUnavailable
            try:
                self.dm.generate_room(room, direction, self.player.world_id, requested_id=dest)
                gen_msg = _c("(The land takes shape as you step into it...)\r\n", DIM)
            except LLMUnavailable:
                # GPU box is off — refuse the move rather than create a
                # stub-room that pollutes the world map permanently.
                return [_output(_c(f"The path {direction} is shrouded — try again later.\r\n", DIM)),
                        self._make_prompt()]
            except Exception as e:
                return [_output(_c(f"The way {direction} resists you ({type(e).__name__}).\r\n", RED)),
                        self._make_prompt()]

        self.player.room_id = dest
        if dest not in self.player.visited_rooms:
            self.player.visited_rooms.append(dest)
        self._advance("move")
        self._persist()
        self._room = None  # invalidate
        new_room = self._load_room()
        msgs: list = [_output(_c(f"You head {direction}.\r\n", DIM))]
        if gen_msg:
            msgs.append(_output(gen_msg))
        msgs.extend([
            _output(render_room(self.player, new_room, co_residents=self._co_residents())),
            _status(self.player),
            self._make_prompt(),
        ])
        return msgs

    def _cmd_map(self, _arg: str) -> list:
        from nachomud.world.map import render_explored_text
        self._advance("look")
        text = render_explored_text(
            self.player.world_id,
            list(self.player.visited_rooms or []),
            current_room_id=self.player.room_id or "",
        )
        return [_output(text + "\r\n"), self._make_prompt()]

    def _cmd_inventory(self, arg: str) -> list:
        p = self.player
        lines = [_c("Equipment:", BOLD)]
        lines.append(f"  Weapon: {p.weapon.name}  ({p.weapon.damage_die or 'no die'})")
        lines.append(f"  Armor:  {p.armor.name}")
        lines.append(f"  Ring:   {p.ring.name}")
        lines.append("")
        lines.append(_c("Gold:", BOLD) + f" {p.gold} gp")
        lines.append("")
        if p.inventory:
            lines.append(_c("Carrying:", BOLD))
            for it in p.inventory:
                lines.append(f"  {it.name}")
        else:
            lines.append(_c("Carrying: nothing.", DIM))
        return [_output("\r\n".join(lines) + "\r\n"), self._make_prompt()]

    def _cmd_stats(self, arg: str) -> list:
        from nachomud.characters.leveling import xp_to_next_level
        from nachomud.rules.stats import mod
        p = self.player
        lines = [_c(f"{p.name} the {p.race} {p.agent_class} (L{p.level})", BOLD + CYAN)]
        lines.append(f"  HP {p.hp}/{p.max_hp}   AC {p.ac}   Speed {p.speed}   Prof +{p.proficiency_bonus}")
        if p.max_ap:
            lines.append(f"  AP {p.ap}/{p.max_ap}")
        if p.max_mp:
            lines.append(f"  MP {p.mp}/{p.max_mp}")
        # XP + progress to next level
        to_next = xp_to_next_level(p)
        if to_next > 100_000_000:  # max level
            lines.append(f"  XP {p.xp} (max level)")
        else:
            lines.append(f"  XP {p.xp}  ({to_next} to L{p.level + 1})")
        lines.append(f"  Gold: {p.gold} gp")
        lines.append("")
        for s in ("STR", "DEX", "CON", "INT", "WIS", "CHA"):
            v = p.stats.get(s, 10)
            m = mod(v)
            sign = "+" if m >= 0 else ""
            lines.append(f"  {_c(s, BOLD)} {v}  ({sign}{m})")
        lines.append("")
        lines.append(f"  Abilities: {', '.join(p.abilities)}")
        lines.append(f"  Saves proficient in: {', '.join(p.save_proficiencies)}")
        return [_output("\r\n".join(lines) + "\r\n"), self._make_prompt()]

    def _cmd_who(self, arg: str) -> list:
        p = self.player
        return [_output(f"You are {_c(p.name, BOLD)} the {p.race} {p.agent_class}, L{p.level}.\r\n"),
                self._make_prompt()]

    def _cmd_help(self, arg: str) -> list:
        lines = [_c("Commands:", BOLD)]
        lines.extend([
            "  look [target]             — describe the room (or examine a target)",
            "  n/s/e/w/u/d, north/south… — move in a direction",
            "  exits                     — list available exits",
            "  inventory (i)             — show carried gear",
            "  stats                     — show full character sheet",
            "  who                       — your name and class",
            "  get <item>                — pick up an item from the room",
            "  drop <item>               — drop an item from your inventory",
            "  equip <item>              — equip a weapon/armor/shield/ring from inventory",
            "  attack <target>           — engage a hostile in combat (turn-based)",
            "  talk <npc>                — strike up a conversation with someone here",
            "  tell <npc> <message>      — say something specific to an NPC",
            "  wares [npc]               — list what shopkeepers are selling",
            "  buy <item> [from <npc>]   — purchase from a shopkeeper present here",
            "  sleep                     — rest until morning (full HP/MP/AP, sets respawn at inns)",
            "  wait [Nm|Nh]              — pass time",
            "  dm <message>              — speak to the Dungeon Master",
            "  save                      — save now",
            "  quit                      — disconnect",
            "  Anything else falls through to the DM as a free-form action.",
        ])
        return [_output("\r\n".join(lines) + "\r\n"), self._make_prompt()]

    def _cmd_save(self, arg: str) -> list:
        self._persist()
        return [_output(_c("Saved.\r\n", GREEN)), self._make_prompt()]

    def _cmd_quit(self, arg: str) -> list:
        self._persist()
        return [_output(_c("Goodbye.\r\n", YELLOW)), ("close", "")]

    def _cmd_get(self, arg: str) -> list:
        if not arg:
            return [_output(_c("Get what?\r\n", RED)), self._make_prompt()]
        items = world_store.items_in_room(self.player.world_id, self.player.room_id)
        match = self._find_item(items, arg)
        if not match:
            return [_output(_c(f"No '{arg}' here.\r\n", RED)), self._make_prompt()]
        world_store.update_item_location(self.player.world_id, match["item_id"], f"inv:{self.player.player_id}")
        from nachomud.world.store import item_from_dict
        it = item_from_dict(match)
        if it is not None:
            self.player.inventory.append(it)
        self._advance("get")
        self._persist()
        return [_output(_c(f"You pick up {match.get('name', '?')}.\r\n", GREEN)), self._make_prompt()]

    def _cmd_drop(self, arg: str) -> list:
        if not arg:
            return [_output(_c("Drop what?\r\n", RED)), self._make_prompt()]
        # Match by name in inventory
        target = None
        for it in self.player.inventory:
            if arg.lower() in it.name.lower():
                target = it
                break
        if not target:
            return [_output(_c(f"You aren't carrying anything matching '{arg}'.\r\n", RED)), self._make_prompt()]
        # Find world-item entry by name (find inventory item in items.json)
        inv_items = world_store.items_in_inventory(self.player.world_id, self.player.player_id)
        match = self._find_item(inv_items, target.name)
        if match:
            world_store.update_item_location(self.player.world_id, match["item_id"], f"room:{self.player.room_id}")
        self.player.inventory.remove(target)
        self._advance("drop")
        self._persist()
        return [_output(_c(f"You drop {target.name}.\r\n", DIM)), self._make_prompt()]

    def _cmd_sleep(self, arg: str) -> list:
        room = self._load_room()
        is_inn = bool(room.flags.get("is_inn"))
        # Advance to next morning 7am
        g = self.player.game_clock
        cur_min = g.get("minute", 480)
        if cur_min < 7 * 60:
            advance_to_min = 7 * 60
            advance_clock(self.player, advance_to_min - cur_min)
        else:
            # to 7am next day
            advance_clock(self.player, (1440 - cur_min) + 7 * 60)
        # Restore HP / MP / AP
        self.player.hp = self.player.max_hp
        self.player.mp = self.player.max_mp
        self.player.ap = self.player.max_ap
        if is_inn:
            self.player.respawn_room = room.id
        self._persist()
        msg = "You rest until morning. Fully restored."
        if is_inn:
            msg += " This inn is now your respawn point."
        return [_output(_c(msg + "\r\n", GREEN)), _status(self.player), self._make_prompt()]

    def _cmd_wait(self, arg: str) -> list:
        # 'wait', 'wait 30m', 'wait 2h'
        minutes = 30
        a = arg.strip().lower()
        if a:
            try:
                if a.endswith("h"):
                    minutes = int(a[:-1]) * 60
                elif a.endswith("m"):
                    minutes = int(a[:-1])
                else:
                    minutes = int(a)
            except ValueError:
                return [_output(_c("Use 'wait', 'wait 30m', or 'wait 2h'.\r\n", RED)), self._make_prompt()]
        advance_clock(self.player, minutes)
        self._persist()
        return [_output(_c(f"Time passes. ({minutes} minutes)\r\n", DIM)), self._make_prompt()]

    def _cmd_equip(self, arg: str) -> list:
        """Equip an item from inventory. Old equipment swaps back in."""
        if not arg:
            return [_output(_c("Equip what? Try 'equip <item>'.\r\n", RED)),
                    self._make_prompt()]
        result = _equip_from_inventory(self.player, arg)
        if not result["ok"]:
            return [_output(_c(result["message"] + "\r\n", RED)), self._make_prompt()]
        self._advance("get")
        self._persist()
        return [_output(_c(result["message"] + "\r\n", GREEN)), _status(self.player),
                self._make_prompt()]

    def _cmd_wares(self, arg: str) -> list:
        """Show what shopkeepers in this room are selling."""
        room = self._load_room()
        hour = hour_from_minute(self.player.game_clock.get("minute", 480))
        present = npcs_in_room(room.npcs, room.id, hour)
        # Filter to a specific NPC if named, else show everyone with wares
        target = arg.strip().lower()
        shown = 0
        lines = []
        for npc, _activity in present:
            if not npc.wares:
                continue
            if target and target not in npc.name.lower():
                continue
            lines.append(_c(f"{npc.name}'s wares:", BOLD + MAGENTA))
            for w in npc.wares:
                price = w.get("price", 0)
                lines.append(f"  {_c(w['name'], YELLOW)} — {price} gp")
            lines.append("")
            shown += 1
        if shown == 0:
            # No matching shopkeeper — let the DM narrate naturally
            # ("Captain Halvar shakes his head, 'I don't trade — try the
            # smithy'") instead of returning a flat error.
            phrase = f"browse the wares of {target}" if target else "browse the wares here"
            return self._cmd_adjudicate(phrase)
        self._advance("wares")
        return [_output("\r\n".join(lines) + "\r\n"), self._make_prompt()]

    def _cmd_buy(self, arg: str) -> list:
        """buy <item> [from <npc>] — purchase from a shopkeeper present in the room."""
        if not arg:
            return [_output(_c("Buy what? Try 'buy <item>' or 'buy <item> from <npc>'.\r\n", RED)),
                    self._make_prompt()]
        # Parse "X from Y" splitting on the last " from "
        item_query = arg
        npc_query = ""
        lower = arg.lower()
        if " from " in lower:
            idx = lower.rindex(" from ")
            item_query = arg[:idx].strip()
            npc_query = arg[idx + len(" from "):].strip()

        room = self._load_room()
        hour = hour_from_minute(self.player.game_clock.get("minute", 480))
        present = [(n, a) for n, a in npcs_in_room(room.npcs, room.id, hour) if n.wares]

        if not present:
            # No shopkeepers in the room — let the DM narrate ("the watchtower
            # captain isn't selling anything, traveler — try the smithy")
            return self._cmd_adjudicate(f"buy {arg}")

        # Find the shopkeeper
        npc = None
        if npc_query:
            for n, _ in present:
                if npc_query.lower() in n.name.lower():
                    npc = n
                    break
            if npc is None:
                return self._cmd_adjudicate(f"buy {item_query} from {npc_query}")
        # Find the item across all shopkeepers if no NPC named
        ware = None
        for n, _ in present:
            if npc and n is not npc:
                continue
            for w in n.wares:
                if item_query.lower() in w["name"].lower():
                    npc = n
                    ware = w
                    break
            if ware:
                break
        if ware is None:
            return self._cmd_adjudicate(f"buy {arg}")

        price = int(ware.get("price", 0))
        if self.player.gold < price:
            return [_output(_c(f"You can't afford that. {ware['name']} costs {price} gp; "
                              f"you have {self.player.gold}.\r\n", RED)),
                    self._make_prompt()]

        # Mint a new world Item entity, place in player inventory.
        import uuid as _uuid
        spec = {k: v for k, v in ware.items() if k != "price"}
        item = Item(**{k: v for k, v in spec.items()
                       if k in {f.name for f in __import__('dataclasses').fields(Item)}})
        item_id = f"shop_{_uuid.uuid4().hex[:10]}"
        world_store.add_item(self.player.world_id, item_id, item, f"inv:{self.player.player_id}")
        self.player.inventory.append(item)
        self.player.gold -= price
        self._advance("buy")
        self._persist()
        return [_output(_c(f"{npc.name} hands you the {item.name}. ", MAGENTA)
                        + _c(f"-{price} gp (now {self.player.gold} gp)\r\n", DIM)),
                self._make_prompt()]

    def _cmd_talk(self, arg: str) -> list:
        return self._npc_dialogue_cmd(arg, default_message="Hello.")

    def _cmd_tell(self, arg: str) -> list:
        return self._npc_dialogue_cmd(arg, default_message="")

    def _npc_dialogue_cmd(self, arg: str, *, default_message: str) -> list:
        """Shared talk/tell logic. Parses 'NPC [about/that] [message]' against
        present NPCs (longest name match wins) and forwards to NPC dialogue.
        Falls through to DM adjudication if the target isn't a present NPC,
        so 'talk wooden post' / 'talk to the deer' get narrated gracefully
        instead of returning a flat error."""
        if not arg:
            return [_output(_c("Speak to whom?\r\n", RED)), self._make_prompt()]
        npc, activity, message = self._find_npc_and_message(arg)
        if npc is None:
            # No NPC matches — let the DM narrate ("the post says nothing",
            # "no one by that name is here, try Captain Halvar"). Keeps the
            # world feeling responsive without hardcoding an object catalog.
            return self._cmd_adjudicate(f"talk to {arg}")
        if not message:
            message = default_message or "Hello."
        reply, _ = self.npc_dialogue.speak(self.player, npc, activity, message)
        self._advance("tell")
        self._persist()
        return [_output(_c(f"{npc.name}: ", BOLD + MAGENTA) + reply + "\r\n"),
                self._make_prompt()]

    def _find_npc_and_message(self, arg: str):
        """Find an NPC by longest-name prefix match in `arg`. Returns
        (npc, activity, message). Strips connector words like 'about', 'that'.
        Falls back to first-word match if no full-name prefix wins."""
        room = self._load_room()
        hour = hour_from_minute(self.player.game_clock.get("minute", 480))
        present = list(npcs_in_room(room.npcs, room.id, hour))
        # Sort longest name first so "Captain Halvar" beats "Captain"
        present_sorted = sorted(present, key=lambda na: -len(na[0].name))
        a_lower = arg.lower()
        # Strip a possessive 's at the end of any token (so "Marta's food" → match Marta)
        a_stripped = a_lower.replace("'s ", " ").replace("’s ", " ")
        for npc, activity in present_sorted:
            name = npc.name.lower()
            if a_stripped == name:
                return npc, activity, ""
            if a_stripped.startswith(name + " "):
                rest = arg[len(npc.name):].strip().lstrip("'’").lstrip("s ").strip()
                rest = _strip_connector(rest)
                return npc, activity, rest
        # Fall back to first-word match against the NPC's distinctive name
        # part(s) only — title words like "Old" or "Captain" don't match
        # alone (so "Old John" doesn't match "Old Marta").
        first_word, _, rest = arg.partition(" ")
        fw = first_word.lower().rstrip("'s").rstrip("’s")
        if fw and fw not in _NAME_TITLES:
            for npc, activity in present_sorted:
                distinctive = _distinctive_name_parts(npc.name)
                if fw in distinctive or any(p.startswith(fw) for p in distinctive):
                    rest = _strip_connector(rest.strip())
                    return npc, activity, rest
        return None, "", ""

    def _cmd_attack(self, arg: str) -> list:
        """Engage a hostile in the current room — switches to combat mode."""
        room = self._load_room()
        # Hydrate room.mobs from the registry so abilities can target them
        living = world_store.mobs_in_room(self.player.world_id, room.id, alive_only=True)
        # Validate target exists
        target_lower = arg.lower()
        target = next((m for m in living if target_lower in m.name.lower()), None)
        if not target:
            return [_output(_c(f"No '{arg}' here to attack.\r\n", RED)), self._make_prompt()]

        room.mobs = list(living)
        self._encounter = Encounter(player=self.player, room=room,
                                    world_id=self.player.world_id,
                                    decider=self.mob_decider,
                                    dm=self.dm)
        msgs = self._encounter.start()
        # If the encounter ended immediately (no living mobs), clean up
        return self._maybe_finish_combat(msgs)

    def _maybe_finish_combat(self, msgs: list) -> list:
        if self._encounter is None or self._encounter.is_active():
            return msgs
        # Combat ended: persist player and clean up
        self._encounter.outcome()
        self._encounter = None
        # Re-emit the explore prompt
        self._room = None  # invalidate (player may have fled)
        self._persist()
        msgs.append(self._make_prompt())
        return msgs

    def _cmd_dm(self, arg: str) -> list:
        message = arg.strip()
        if not message:
            return [_output(_c("Speak to the DM about what?\r\n", RED)), self._make_prompt()]
        room = self._load_room()
        reply = self.dm.respond(self.player, room, message)
        self._advance("dm")
        self._persist()
        return [_output(_c("DM: ", BOLD + MAGENTA) + reply + "\r\n"), self._make_prompt()]

    def _cmd_adjudicate(self, action: str) -> list:
        """Free-form action adjudicated by the DM (Phase 10).
        May include a skill check rolled against the player's stats, plus any
        engine-validated state actions (consume_item, restore_hp, set_flag,
        engage_combat)."""
        room = self._load_room()
        result = self.dm.adjudicate(self.player, room, action)
        self._advance("dm")
        self._persist()
        msgs: list = [_output(_c("DM: ", BOLD + MAGENTA) + result["narrate"] + "\r\n")]
        sc = result.get("skill_check_result")
        if sc:
            tag = _c("✓ success", GREEN) if sc["success"] else _c("✗ fail", RED)
            roll_line = (f"  [{sc['stat']} check, DC {sc['dc']}: "
                         f"d20={sc['roll']} {sc['modifier']:+d} = {sc['total']}] {tag}\r\n")
            msgs.append(_output(_c(roll_line, DIM)))
            if sc["narration"]:
                msgs.append(_output(_c("DM: ", BOLD + MAGENTA) + sc["narration"] + "\r\n"))
        combat_intent = None
        # Render any applied state changes so the player sees what really happened
        for act in result.get("actions_applied", []) or []:
            kind = act.get("type")
            if kind == "consumed":
                msgs.append(_output(_c(f"  · {act['item']} consumed.\r\n", DIM + GREEN)))
            elif kind == "restored":
                msgs.append(_output(_c(f"  · +{act['amount']} {act['stat']}.\r\n", DIM + GREEN)))
                if act["stat"] in ("HP", "MP", "AP"):
                    msgs.append(_status(self.player))
            elif kind == "flag_set":
                msgs.append(_output(_c(f"  · ({act['flag']} = {act['value']})\r\n", DIM)))
            elif kind == "got":
                msgs.append(_output(_c(f"  · picked up {act['item']}.\r\n", DIM + GREEN)))
            elif kind == "dropped":
                msgs.append(_output(_c(f"  · dropped {act['item']}.\r\n", DIM)))
            elif kind == "equipped":
                msgs.append(_output(_c(
                    f"  · equipped {act['item']} ({act['slot']}).\r\n", DIM + GREEN)))
                msgs.append(_status(self.player))
            elif kind == "bought":
                msgs.append(_output(_c(
                    f"  · bought {act['item']} from {act['from']} for {act['price']} gp.\r\n",
                    DIM + GREEN)))
                msgs.append(_status(self.player))
            elif kind == "combat_intent":
                combat_intent = act
        if result.get("hint"):
            msgs.append(_output(_c(f"  (You file this away: \"{result['hint']}\")\r\n", DIM)))

        # If the DM signaled combat, escalate immediately — append the
        # combat-start messages directly after the narration.
        if combat_intent is not None:
            msgs.extend(self._cmd_attack(combat_intent["target"]))
        else:
            msgs.append(self._make_prompt())
        return msgs

    # ── Generic helpers ──

    def _find_item(self, items: list[dict], query: str) -> dict | None:
        q = query.lower()
        for it in items:
            if q in it.get("name", "").lower():
                return it
        return None
