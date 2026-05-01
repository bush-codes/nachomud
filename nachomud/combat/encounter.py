"""Turn-based combat encounter.

State machine: START → ROUND_LOOP → END (victory|defeat|fled). The encounter
hooks into the same dispatch model as Game: while combat is active, Game
forwards player input to Encounter.handle_player_input, which resolves the
player's action and runs all subsequent mob turns until the next player
turn or combat end. Each enter/exit transition emits a list of session
messages.

Mobs are loaded from world_store at combat start and synced back after
every action so death/HP changes persist immediately.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from collections.abc import Callable

import nachomud.combat.abilities as abilities_mod
import nachomud.settings as config
import nachomud.world.store as world_store
from nachomud.style import _c, BOLD, CYAN, DIM, GREEN, MAGENTA, RED, YELLOW
from nachomud.rules.dice import roll_d20
from nachomud.models import AgentState, Mob, Room
from nachomud.rules.stats import mod as stat_mod


# ── Utilities ──

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


# ── Mob action selection (rules-based for v1; LLM hook for v2) ──

MobDecider = Callable[[Mob, AgentState, Room], tuple[str, str]]
"""(mob, target_player, room) -> (ability_name, target_name)"""


def default_mob_decider(mob: Mob, target: AgentState, room: Room) -> tuple[str, str]:
    """Pick the strongest available ability against the player.

    Priority: damage abilities first (cleave, smite, holy_bolt, attack), heal at
    low HP, status if available. Falls back to plain attack.
    """
    abil = list(mob.abilities or [])
    if not abil:
        return "attack", target.name
    # Heal if low HP and has heal-style ability
    if mob.hp <= max(1, mob.max_hp // 4):
        for a in ("lay_on_hands", "heal", "cure"):
            if a in abil:
                return a, mob.name
    # Damage abilities ordered by power
    for a in ("cleave", "consecrate", "arcane_storm", "smite", "holy_bolt", "missile",
              "aimed_shot", "backstab", "volley", "attack"):
        if a in abil:
            return a, target.name
    # Anything else
    return abil[0], target.name


# ── Encounter ──

@dataclass
class Initiative:
    """One participant's initiative slot."""
    name: str
    is_player: bool
    roll: int  # d20 + modifier
    mob_id: str = ""  # if not is_player


@dataclass
class Encounter:
    player: AgentState
    room: Room
    world_id: str
    decider: MobDecider | None = None
    # Optional DM ref so the player can chat mid-combat
    dm: object | None = None

    # Internal
    mob_dict: dict[str, Mob] = field(default_factory=dict)
    order: list[Initiative] = field(default_factory=list)
    turn_idx: int = 0
    round_num: int = 1
    state: str = "active"  # "active" | "victory" | "defeat" | "fled"

    def __post_init__(self):
        if self.decider is None:
            self.decider = default_mob_decider

    # ── Public API ──

    def start(self) -> list:
        """Roll initiative, populate room.mobs, advance to player's first turn."""
        living_mobs = world_store.mobs_in_room(self.world_id, self.room.id, alive_only=True)
        self.mob_dict = {m.mob_id: m for m in living_mobs}
        self.room.mobs = list(self.mob_dict.values())

        if not self.mob_dict:
            self.state = "victory"
            return [_output(_c("There is no one here to fight.\r\n", DIM))]

        # Initiative: 1d20 + DEX mod for everyone
        rolls: list[Initiative] = []
        p_mod = stat_mod(self.player.stats.get("DEX", 10))
        rolls.append(Initiative(name=self.player.name, is_player=True,
                                roll=roll_d20() + p_mod))
        for mob_id, m in self.mob_dict.items():
            m_dex = stat_mod((m.stats or {}).get("DEX", 10)) if m.stats else 0
            rolls.append(Initiative(name=m.name, is_player=False,
                                    roll=roll_d20() + m_dex, mob_id=mob_id))
        # Sort high → low. Ties: player first.
        rolls.sort(key=lambda i: (i.roll, i.is_player), reverse=True)
        self.order = rolls
        self.turn_idx = 0

        msgs: list = [
            _mode("combat"),
            _output(self._render_initiative()),
        ]
        msgs.extend(self._advance_until_player_turn())
        return msgs

    def handle_player_input(self, text: str) -> list:
        """Resolve player action, advance through mob turns to next player turn."""
        if self.state != "active":
            return []

        text = text.strip()
        if not text:
            return [self._make_prompt()]

        cmd, _, arg = text.partition(" ")
        cmd_lower = cmd.lower()
        arg = arg.strip()

        if cmd_lower in ("flee", "run", "escape"):
            return self._flee()
        if cmd_lower in ("look", "l"):
            return [_output(self._render_combatants()), self._make_prompt()]
        if cmd_lower in ("status", "stats"):
            return [_output(self._render_status()), self._make_prompt()]
        if cmd_lower in ("help", "?"):
            return [_output(self._render_help()), self._make_prompt()]
        # DM chat mid-combat — non-action, doesn't consume the player's turn
        if cmd_lower in ("dm", "ask"):
            if not arg:
                return [_output(_c("Speak to the DM about what?\r\n", RED)), self._make_prompt()]
            if self.dm is None:
                return [_output(_c("The DM is silent in the heat of battle.\r\n", DIM)),
                        self._make_prompt()]
            try:
                reply = self.dm.respond(self.player, self.room, arg)
            except Exception:
                reply = "(The DM's voice falters in the chaos.)"
            return [_output(_c("DM: ", BOLD + MAGENTA) + reply + "\r\n"),
                    self._make_prompt()]

        # Treat "attack <target>" and "<ability> <target>" identically
        ability_name = cmd_lower
        target_name = arg
        if ability_name == "attack":
            pass  # works directly
        elif ability_name not in (self.player.abilities or []):
            return [_output(_c(f"You don't have the ability '{ability_name}'. "
                              f"Available: {', '.join(self.player.abilities)}\r\n", RED)),
                    self._make_prompt()]

        # Resolve via abilities.py
        rooms_dict = {self.room.id: self.room}
        events = abilities_mod.resolve_ability(
            self.player, ability_name, target_name, self.room,
            self.round_num, [self.player], rooms_dict,
        )
        msgs: list = [_output(self._render_event(events[0]) + "\r\n")]

        # Persist mob state (HP, alive)
        self._sync_mobs()

        # Check victory
        if all(not m.alive for m in self.mob_dict.values()):
            return msgs + self._end_victory()

        # Advance turn
        self.turn_idx += 1
        msgs.extend(self._advance_until_player_turn())
        return msgs

    def is_active(self) -> bool:
        return self.state == "active"

    def outcome(self) -> str:
        return self.state

    # ── Internals ──

    def _render_initiative(self) -> str:
        lines = [_c("⚔  Combat begins!  ⚔", BOLD + RED), _c("Initiative:", BOLD)]
        for i in self.order:
            tag = _c(i.name, GREEN if i.is_player else RED)
            lines.append(f"  {i.roll}  {tag}")
        return "\r\n".join(lines) + "\r\n"

    def _render_combatants(self) -> str:
        lines = [_c("Combatants:", BOLD)]
        lines.append(f"  {_c(self.player.name, GREEN)} HP {self.player.hp}/{self.player.max_hp}  AC {self.player.ac}")
        for m in self.mob_dict.values():
            tag = _c(m.name, RED) if m.alive else _c(f"{m.name} (slain)", DIM)
            line = f"  {tag}"
            if m.alive:
                line += f" HP {m.hp}/{m.max_hp}  AC {m.ac}"
            lines.append(line)
        return "\r\n".join(lines) + "\r\n"

    def _render_status(self) -> str:
        p = self.player
        lines = [
            _c(f"Round {self.round_num}", BOLD + CYAN),
            f"  HP {p.hp}/{p.max_hp}   AC {p.ac}   "
            f"{('AP ' + str(p.ap) + '/' + str(p.max_ap)) if p.max_ap else ''}"
            f"{(' MP ' + str(p.mp) + '/' + str(p.max_mp)) if p.max_mp else ''}",
            f"  Abilities: {', '.join(p.abilities)}",
        ]
        return "\r\n".join(lines) + "\r\n"

    def _render_help(self) -> str:
        return (
            _c("Combat commands:", BOLD) + "\r\n"
            "  attack <target>      — basic weapon attack\r\n"
            "  <ability> [target]   — use a class ability (defend, heal, smite, etc.)\r\n"
            "  look                 — show all combatants and HP/AC\r\n"
            "  status               — your stats this round\r\n"
            "  dm <message>         — speak to the DM (no time cost in combat)\r\n"
            "  flee                 — try to run (parting shots from each engaged mob)\r\n"
        )

    def _render_event(self, event) -> str:
        # Color combat events: hits red, crits magenta, misses dim
        text = event.result if hasattr(event, "result") else str(event)
        if "CRIT" in text:
            return _c(text, MAGENTA)
        if "miss" in text.lower() or "resist" in text.lower():
            return _c(text, DIM)
        return text

    def _make_prompt(self) -> tuple[str, str]:
        p = self.player
        bar = f"HP {p.hp}/{p.max_hp}"
        if p.max_ap:
            bar += f" AP {p.ap}/{p.max_ap}"
        if p.max_mp:
            bar += f" MP {p.mp}/{p.max_mp}"
        return _prompt(_c(f"[combat r{self.round_num}] [{bar}] ", DIM) +
                       _c(f"{p.name}> ", GREEN))

    def _advance_until_player_turn(self) -> list:
        """Run mob turns; stop when it's the player's turn (or combat ended)."""
        msgs: list = []
        while self.state == "active":
            if self.turn_idx >= len(self.order):
                # End of round
                self.turn_idx = 0
                self.round_num += 1
                msgs.append(_output(_c(f"--- Round {self.round_num} ---\r\n", DIM)))
                continue

            turn = self.order[self.turn_idx]
            if turn.is_player:
                msgs.append(_status(self.player))
                msgs.append(self._make_prompt())
                return msgs

            # Mob turn
            mob = self.mob_dict.get(turn.mob_id)
            if mob is None or not mob.alive:
                self.turn_idx += 1
                continue
            msgs.extend(self._mob_turn(mob))
            # Check defeat after mob turn
            if not self.player.alive or self.player.hp <= 0:
                msgs.extend(self._on_player_zero())
                if self.state == "defeat":
                    return msgs
            self.turn_idx += 1
        return msgs

    def _mob_turn(self, mob: Mob) -> list:
        ability_name, _target_name = self.decider(mob, self.player, self.room)
        # Mob "attack" against player: simple d20+attack vs AC, weapon_die + damage_bonus
        if ability_name == "attack":
            return self._mob_basic_attack(mob)
        # For now, all other abilities reduce to a basic attack — Phase 11/polish can add
        # mob ability variety. The bones are here for future expansion.
        return self._mob_basic_attack(mob)

    def _mob_basic_attack(self, mob: Mob) -> list:
        atk_bonus = stat_mod((mob.stats or {}).get("STR", 10)) + mob.proficiency_bonus
        d20 = roll_d20()
        total = d20 + atk_bonus
        if d20 == 1:
            return [_output(_c(f"{mob.name} swings at {self.player.name} ({d20}+{atk_bonus}={total}) — critical miss!\r\n", DIM))]
        crit = d20 == 20
        if not crit and total < self.player.ac:
            return [_output(_c(f"{mob.name} swings at {self.player.name} ({d20}+{atk_bonus}={total} vs AC {self.player.ac}) — miss.\r\n", DIM))]
        # Damage
        from nachomud.rules.dice import roll_dice_doubled, roll_detail
        die = mob.damage_die or "1d4"
        dmg = roll_dice_doubled(die) if crit else roll_detail(die).total
        dmg += mob.damage_bonus
        dmg = max(1, dmg)
        from nachomud.characters.effects import modify_incoming_damage
        dmg = modify_incoming_damage(self.player, dmg)
        self.player.hp = max(0, self.player.hp - dmg)
        crit_tag = " CRIT!" if crit else ""
        text = (f"{mob.name} hits {self.player.name} ({d20}+{atk_bonus}={total} vs AC {self.player.ac}){crit_tag} "
                f"for {dmg} damage. ({self.player.name} HP {self.player.hp}/{self.player.max_hp})")
        color = MAGENTA if crit else RED
        return [_output(_c(text + "\r\n", color))]

    def _sync_mobs(self) -> None:
        for m in self.mob_dict.values():
            world_store.update_mob(self.world_id, m)

    def _on_player_zero(self) -> list:
        p = self.player
        # Half-Orc relentless: drops to 1 HP once per long rest
        if p.race == "Half-Orc" and not p.dm_context.get("relentless_used"):
            p.hp = 1
            p.dm_context["relentless_used"] = True
            return [_output(_c(f"{p.name}'s relentless endurance kicks in! Back to 1 HP.\r\n", BOLD + GREEN))]
        # Otherwise: dead. Respawn flow.
        return self._end_defeat()

    def _flee(self) -> list:
        # Pick a random adjacent room. Each engaged mob gets a parting shot.
        msgs: list = [_output(_c(f"{self.player.name} attempts to flee!\r\n", YELLOW))]
        for m in self.mob_dict.values():
            if m.alive:
                # Mob ai_state shifts to pursue (Phase 8 mobility uses this)
                m.ai_state = "pursue"
                m.ai_target = self.player.player_id
                # Parting shot
                msgs.extend(self._mob_basic_attack(m))
                if self.player.hp <= 0:
                    msgs.extend(self._on_player_zero())
                    return msgs
        # Move to adjacent room
        exits = list(self.room.exits.items())
        if not exits:
            msgs.append(_output(_c("There's no way out!\r\n", RED)))
            self.turn_idx += 1
            msgs.extend(self._advance_until_player_turn())
            return msgs
        # Pick the first exit (deterministic)
        direction, dest = exits[0]
        if not world_store.room_exists(self.world_id, dest):
            msgs.append(_output(_c("That way is uncharted; you can't escape there.\r\n", RED)))
            self.turn_idx += 1
            msgs.extend(self._advance_until_player_turn())
            return msgs
        self.player.room_id = dest
        self.state = "fled"
        self._sync_mobs()
        msgs.append(_output(_c(f"You flee {direction}!\r\n", GREEN)))
        msgs.append(_mode("explore"))
        return msgs

    def _end_victory(self) -> list:
        from nachomud.characters.leveling import apply_all_pending_level_ups, render_level_up
        # Award XP from the slain mobs
        xp = sum(m.xp_value for m in self.mob_dict.values())
        self.player.xp += xp
        self._sync_mobs()
        self.state = "victory"
        msgs = [
            _output(_c(f"\r\n⚔  Victory! ⚔  +{xp} XP.\r\n", BOLD + GREEN)),
        ]
        # Level-up check: walk through any thresholds crossed by this XP gain
        for lu in apply_all_pending_level_ups(self.player):
            text = render_level_up(lu, self.player.name).replace("\n", "\r\n")
            msgs.append(_output(_c("\r\n" + text + "\r\n", BOLD + YELLOW)))
        msgs.append(_status(self.player))
        msgs.append(_mode("explore"))
        return msgs

    def _end_defeat(self) -> list:
        p = self.player
        # 10% XP loss
        loss = int(p.xp * config.DEATH_XP_PENALTY_PCT)
        p.xp = max(0, p.xp - loss)
        # Restore HP, move to respawn room
        p.hp = p.max_hp
        p.mp = p.max_mp
        p.ap = p.max_ap
        p.alive = True
        p.room_id = p.respawn_room or "silverbrook.inn"
        # Reset relentless trigger (counts as a long rest)
        if "relentless_used" in p.dm_context:
            del p.dm_context["relentless_used"]
        self._sync_mobs()
        self.state = "defeat"
        return [
            _output(_c(f"\r\n💀 You fall in battle. (-{loss} XP)\r\n", BOLD + RED)),
            _output(_c(f"You wake at {p.respawn_room}, restored.\r\n", DIM)),
            _status(self.player),
            _mode("explore"),
        ]
