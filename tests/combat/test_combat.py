"""Tests for combat.py — turn-based encounter state machine."""
from __future__ import annotations

import pytest

import nachomud.rules.dice as dice
import nachomud.characters.save as player_mod
import nachomud.world.starter as starter
import nachomud.world.store as world_store
from nachomud.characters.character import create_character
from nachomud.combat.encounter import Encounter, default_mob_decider
from nachomud.ai.dm import DM
from nachomud.engine.game import Game
from nachomud.models import Item, Mob
from nachomud.ai.npc import NPCDialogue
from nachomud.rules.stats import Stats


@pytest.fixture
def world(tmp_path, monkeypatch):
    monkeypatch.setattr(world_store, "DATA_ROOT", str(tmp_path / "world"))
    monkeypatch.setattr(player_mod, "DATA_ROOT", str(tmp_path / "players"))
    starter.seed_world("default")
    return tmp_path


@pytest.fixture
def player(world):
    s = Stats(STR=15, DEX=12, CON=14, INT=8, WIS=10, CHA=13)
    a = create_character("Aric", "Dwarf", "Warrior", s,
                         player_id="p1", respawn_room="silverbrook.inn", world_id="default")
    a.room_id = "silverbrook.inn"
    player_mod.save_player(a)
    return a


def _stub_dm():
    return DM(llm=lambda s, u: "ok.")


def _stub_npc():
    return NPCDialogue(llm=lambda s, u: "Aye.", summarizer=lambda s, u: "summary.")


def _spawn_goblin(world_id, room_id, mob_id="goblin_1", hp=10, ac=11, decider_target="Aric"):
    m = Mob(
        name="Goblin", hp=hp, max_hp=hp, atk=2, ac=ac, level=1,
        stats={"STR": 8, "DEX": 14, "CON": 10, "INT": 8, "WIS": 8, "CHA": 6},
        damage_die="1d4", damage_bonus=2,
        faction="goblin_clan", aggression=7,
        home_room=room_id, current_room=room_id,
        zone_tag="silverbrook_town", mob_id=mob_id, kind="goblin",
        abilities=["attack"], xp_value=25,
    )
    world_store.add_mob(world_id, m)
    return m


def _text(msgs) -> str:
    return "".join(m[1] for m in msgs if isinstance(m, tuple) and m[0] == "output")


def _modes(msgs) -> list[str]:
    return [m[1] for m in msgs if isinstance(m, tuple) and m[0] == "mode"]


# ── Direct Encounter API ──

def test_initiative_is_rolled_for_all_participants(player):
    _spawn_goblin(player.world_id, player.room_id)
    room = world_store.load_room(player.world_id, player.room_id)
    enc = Encounter(player=player, room=room, world_id=player.world_id)
    msgs = enc.start()
    text = _text(msgs)
    assert "Combat begins" in text
    assert "Initiative" in text
    assert player.name in text
    assert "Goblin" in text
    assert "combat" in _modes(msgs)


def test_full_combat_player_wins(player):
    dice.seed(1)  # deterministic
    _spawn_goblin(player.world_id, player.room_id, hp=4, ac=5)  # easy mob
    room = world_store.load_room(player.world_id, player.room_id)
    enc = Encounter(player=player, room=room, world_id=player.world_id)
    enc.start()

    # Loop: attack until victory
    for _ in range(10):
        if not enc.is_active():
            break
        msgs = enc.handle_player_input("attack goblin")
    assert enc.outcome() == "victory"
    text = _text(msgs)
    assert "Victory" in text
    assert player.xp > 0


def test_full_combat_player_dies_and_respawns(player):
    dice.seed(0xDEAD)
    # Spawn a brutal mob the player can't survive
    _spawn_goblin(player.world_id, player.room_id, hp=999, ac=99)
    room = world_store.load_room(player.world_id, player.room_id)
    starting_room = player.room_id
    player.respawn_room = "silverbrook.inn"
    enc = Encounter(player=player, room=room, world_id=player.world_id)
    enc.start()
    while enc.is_active():
        msgs = enc.handle_player_input("attack goblin")
    assert enc.outcome() == "defeat"
    # Player respawned at inn with full HP
    assert player.hp == player.max_hp
    assert player.room_id == "silverbrook.inn"


def test_flee_exits_combat_and_moves_player(player):
    _spawn_goblin(player.world_id, player.room_id, hp=999, ac=20)
    room = world_store.load_room(player.world_id, player.room_id)
    enc = Encounter(player=player, room=room, world_id=player.world_id)
    enc.start()
    msgs = enc.handle_player_input("flee")
    # Either the mob killed the player on the parting shot or they escaped.
    assert enc.outcome() in ("fled", "defeat")
    if enc.outcome() == "fled":
        assert player.room_id != room.id
        # Mob ai_state should be 'pursue' for the goblin
        m = world_store.get_mob(player.world_id, "goblin_1")
        assert m.ai_state == "pursue"


def test_combat_with_no_mobs_immediately_ends(player):
    # No mobs spawned in player's room
    room = world_store.load_room(player.world_id, player.room_id)
    enc = Encounter(player=player, room=room, world_id=player.world_id)
    msgs = enc.start()
    assert enc.outcome() == "victory"
    assert "no one here" in _text(msgs).lower()


def test_mob_state_persists_across_combat(player):
    dice.seed(1)
    _spawn_goblin(player.world_id, player.room_id, hp=4, ac=5)
    room = world_store.load_room(player.world_id, player.room_id)
    enc = Encounter(player=player, room=room, world_id=player.world_id)
    enc.start()
    while enc.is_active():
        enc.handle_player_input("attack goblin")
    # Check mobs.json reflects death
    m = world_store.get_mob(player.world_id, "goblin_1")
    assert m is not None
    assert not m.alive


def test_unknown_ability_rejected(player):
    _spawn_goblin(player.world_id, player.room_id, ac=99)
    room = world_store.load_room(player.world_id, player.room_id)
    enc = Encounter(player=player, room=room, world_id=player.world_id)
    enc.start()
    msgs = enc.handle_player_input("fireball goblin")  # warrior doesn't have fireball
    assert "don't have" in _text(msgs).lower() or "ability" in _text(msgs).lower()


def test_default_mob_decider_picks_attack(player):
    mob = Mob(name="g", hp=10, max_hp=10, atk=3, abilities=["attack"])
    a, t = default_mob_decider(mob, player, None)
    assert a == "attack"
    assert t == player.name


def test_default_mob_decider_heals_at_low_hp(player):
    mob = Mob(name="g", hp=2, max_hp=20, atk=3, abilities=["attack", "heal"])
    a, t = default_mob_decider(mob, player, None)
    assert a == "heal"
    assert t == mob.name


# ── Through Game ──

def test_game_attack_triggers_combat(player):
    _spawn_goblin(player.world_id, player.room_id)
    g = Game(player=player, dm=_stub_dm(), npc_dialogue=_stub_npc())
    g.start()
    msgs = g.handle("attack goblin")
    assert "Combat begins" in _text(msgs)
    assert g._encounter is not None
    assert g._encounter.is_active()


def test_game_attack_unknown_target(player):
    g = Game(player=player, dm=_stub_dm(), npc_dialogue=_stub_npc())
    g.start()
    msgs = g.handle("attack dragon")
    assert "no" in _text(msgs).lower() or "here" in _text(msgs).lower()
    assert g._encounter is None


def test_game_combat_input_routed_to_encounter(player):
    dice.seed(1)
    _spawn_goblin(player.world_id, player.room_id, hp=4, ac=5)
    g = Game(player=player, dm=_stub_dm(), npc_dialogue=_stub_npc())
    g.start()
    g.handle("attack goblin")
    # While in combat, "look" should render combatants (not the room)
    msgs = g.handle("look")
    assert "Combatants" in _text(msgs) or "HP" in _text(msgs)


def test_game_combat_ends_returns_to_explore(player):
    dice.seed(1)
    _spawn_goblin(player.world_id, player.room_id, hp=2, ac=5)
    g = Game(player=player, dm=_stub_dm(), npc_dialogue=_stub_npc())
    g.start()
    g.handle("attack goblin")
    while g._encounter is not None and g._encounter.is_active():
        g.handle("attack goblin")
    assert g._encounter is None
    # Now "look" returns to room rendering
    msgs = g.handle("look")
    assert "Bronze Hart" in _text(msgs) or "Inn" in _text(msgs)
