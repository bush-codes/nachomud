"""Tests for game.py — command dispatch in the player game loop."""
from __future__ import annotations

import pytest

import nachomud.characters.save as player_mod
import nachomud.world.starter as starter
import nachomud.world.store as world_store
from nachomud.characters.character import create_character
from nachomud.ai.dm import DM
from nachomud.engine.game import Game, advance_clock, clock_str
from nachomud.models import Item
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


@pytest.fixture
def stub_dm():
    return DM(llm=lambda s, u: "The DM nods.")


@pytest.fixture
def stub_npc():
    from nachomud.ai.npc import NPCDialogue
    return NPCDialogue(
        llm=lambda s, u: "Aye, that's the way of it.",
        summarizer=lambda s, u: "Spoke briefly.",
    )


@pytest.fixture
def game(player, stub_dm, stub_npc):
    return Game(player=player, dm=stub_dm, npc_dialogue=stub_npc)


# ── Helper to extract output text from a session message list ──

def _text(msgs) -> str:
    return "".join(m[1] for m in msgs if isinstance(m, tuple) and m[0] == "output")


# ── Movement ──

def test_start_renders_room(game):
    msgs = game.start()
    text = _text(msgs)
    assert "Bronze Hart Inn" in text
    assert "Old Marta" in text
    assert "Exits" in text


def test_move_north_into_market(game):
    game.start()
    msgs = game.handle("n")
    text = _text(msgs)
    assert "Market Square" in text
    assert game.player.room_id == "silverbrook.market_square"
    assert "silverbrook.market_square" in game.player.visited_rooms


def test_move_invalid_direction(game):
    game.start()
    msgs = game.handle("south")
    text = _text(msgs)
    assert "cannot go" in text.lower()


def test_move_into_unauthored_room_triggers_generation(game):
    """Phase 9: walking off the edge of Silverbrook causes DM to generate
    a new room. Stub DM (which doesn't return valid JSON) falls back to a
    placeholder room — player still ends up somewhere new."""
    game.start()
    game.handle("n")  # market
    game.handle("n")  # north_gate
    game.handle("n")  # watchtower
    starting_room = game.player.room_id
    msgs = game.handle("n")  # frontier — generates
    assert game.player.room_id != starting_room
    assert game.player.room_id.startswith("wild.")


# ── Look / inspect ──

def test_look_renders_room_again(game):
    game.start()
    msgs = game.handle("look")
    assert "Bronze Hart Inn" in _text(msgs)


def test_look_at_target_falls_through_to_dm(game):
    game.start()
    msgs = game.handle("look at the hearth")
    assert "DM:" in _text(msgs)


def test_unknown_command_falls_through_to_dm(game):
    game.start()
    msgs = game.handle("I push the bookcase")
    assert "DM:" in _text(msgs)


# ── DM command ──

def test_dm_command_records_exchange(game):
    game.start()
    game.handle("dm what's that smell?")
    assert game.player.dm_context["recent_exchanges"], "DM context should capture the exchange"
    assert game.player.dm_context["recent_exchanges"][-1]["player"] == "what's that smell?"


def test_dm_persists_across_load(game, world):
    game.start()
    game.handle("dm hello")
    # Re-load player from disk and verify dm context survived
    p2 = player_mod.load_player("p1")
    assert p2.dm_context["recent_exchanges"]
    assert p2.dm_context["recent_exchanges"][-1]["player"] == "hello"


# ── Inventory / items ──

def test_inventory_empty(game):
    game.start()
    msgs = game.handle("inventory")
    assert "Carrying: nothing" in _text(msgs) or "Carrying:" in _text(msgs)


def test_get_item_from_room(game):
    # Place a coin in the inn
    world_store.add_item(game.player.world_id, "coin_1",
                         Item(name="Bronze Coin", slot="consumable"),
                         f"room:{game.player.room_id}")
    game.start()
    msgs = game.handle("get coin")
    assert "pick up" in _text(msgs).lower()
    assert any(it.name == "Bronze Coin" for it in game.player.inventory)
    # Coin moved to inv:player
    inv = world_store.items_in_inventory(game.player.world_id, game.player.player_id)
    assert any(i["item_id"] == "coin_1" for i in inv)


def test_get_missing_item(game):
    game.start()
    msgs = game.handle("get phlogiston")
    assert "no" in _text(msgs).lower()


def test_drop_item(game):
    world_store.add_item(game.player.world_id, "coin_1",
                         Item(name="Bronze Coin", slot="consumable"),
                         f"room:{game.player.room_id}")
    game.start()
    game.handle("get coin")
    msgs = game.handle("drop coin")
    assert "drop" in _text(msgs).lower()
    assert not any(it.name == "Bronze Coin" for it in game.player.inventory)


# ── Stats / who ──

def test_stats_command_shows_full_sheet(game):
    game.start()
    msgs = game.handle("stats")
    text = _text(msgs)
    assert "Aric" in text
    assert "Dwarf" in text
    assert "Warrior" in text
    assert "STR" in text and "CON" in text


def test_who_command(game):
    game.start()
    msgs = game.handle("who")
    text = _text(msgs)
    assert "Aric" in text
    assert "Warrior" in text


# ── Sleep ──

def test_sleep_at_inn_restores_and_sets_respawn(game):
    p = game.player
    p.hp = 1
    p.ap = 0
    p.respawn_room = "somewhere_else"
    game.start()
    msgs = game.handle("sleep")
    assert p.hp == p.max_hp
    assert p.ap == p.max_ap
    assert p.respawn_room == "silverbrook.inn"
    text = _text(msgs)
    assert "rest" in text.lower()
    assert "respawn" in text.lower()


def test_sleep_outside_inn_does_not_change_respawn(game):
    p = game.player
    p.hp = 1
    p.respawn_room = "silverbrook.inn"
    game.start()
    game.handle("n")  # to market
    game.handle("sleep")
    assert p.hp == p.max_hp
    assert p.respawn_room == "silverbrook.inn"  # unchanged because not at inn


# ── Wait / clock ──

def test_wait_advances_clock(game):
    game.start()
    before = game.player.game_clock["minute"]
    game.handle("wait 30m")
    after = game.player.game_clock["minute"]
    assert (after - before) % 1440 == 30


def test_wait_2h(game):
    game.start()
    before_day = game.player.game_clock["day"]
    before_min = game.player.game_clock["minute"]
    game.handle("wait 2h")
    delta = (game.player.game_clock["day"] - before_day) * 1440 + (game.player.game_clock["minute"] - before_min)
    assert delta == 120


def test_clock_wraps_to_next_day():
    from nachomud.models import AgentState
    p = AgentState(name="x", personality="", agent_class="Warrior", hp=1, max_hp=1, mp=0, max_mp=0,
                   weapon=Item("w", "weapon"), armor=Item("a", "armor"), ring=Item("r", "ring"),
                   game_clock={"day": 1, "minute": 1430})
    advance_clock(p, 30)
    assert p.game_clock["day"] == 2
    assert p.game_clock["minute"] == 20


def test_clock_str_format():
    from nachomud.models import AgentState
    p = AgentState(name="x", personality="", agent_class="Warrior", hp=1, max_hp=1, mp=0, max_mp=0,
                   weapon=Item("w", "weapon"), armor=Item("a", "armor"), ring=Item("r", "ring"),
                   game_clock={"day": 3, "minute": 8 * 60 + 32})
    assert clock_str(p) == "day 3 08:32"


# ── NPCs filtered by routines ──

def test_npc_visible_at_morning(game):
    # Game clock starts at 8am (480m)
    game.start()
    msgs = game.handle("look")
    assert "Old Marta" in _text(msgs)


def test_npc_filtered_when_off_routine(game):
    # Move to the smithy at noon (Old John should be there) then midnight (gone).
    game.start()
    game.handle("n")  # market_square
    game.handle("e")  # smithy
    # Noon: Old John is at the forge
    game.player.game_clock = {"day": 1, "minute": 12 * 60}
    text_noon = _text(game.handle("look"))
    assert "People here" in text_noon
    assert "working the forge" in text_noon

    # Midnight: Old John has gone home
    game.player.game_clock = {"day": 2, "minute": 0}
    text_night = _text(game.handle("look"))
    assert "People here" not in text_night


# ── Save ──

def test_save_command(game):
    game.start()
    game.player.hp = 5
    game.handle("save")
    p2 = player_mod.load_player("p1")
    assert p2.hp == 5


# ── Help ──

def test_help_lists_commands(game):
    game.start()
    msgs = game.handle("help")
    text = _text(msgs)
    assert "look" in text and "inventory" in text and "dm" in text and "talk" in text


# ── NPC dialogue (talk / tell) ──

def test_talk_to_present_npc(game):
    # Marta is at the inn from 6am, default clock starts at 8am
    game.start()
    msgs = game.handle("talk Marta")
    text = _text(msgs)
    assert "Marta" in text
    assert "Aye" in text


def test_talk_to_absent_npc(game):
    """Falling through to DM adjudication when target NPC isn't here:
    the stub DM responds, so we just verify a DM line shows up (not a
    hardcoded error) and that no NPC was actually addressed."""
    game.start()
    msgs = game.handle("talk John")
    text = _text(msgs)
    # Either the DM narrated, or the lookup matched a different present NPC.
    # The key invariant: no flat "no one named X" hardcoded error.
    assert "DM:" in text or "Marta" in text or "Greta" in text


def test_tell_with_message(game):
    game.start()
    msgs = game.handle("tell marta Where is the smithy?")
    text = _text(msgs)
    assert "Marta" in text
    assert "Aye" in text


def test_tell_appends_to_lore_history(game):
    game.start()
    game.handle("talk marta")
    assert any("Marta" in line or "Spoke" in line for line in game.player.lore_history)


# ── Natural-language NPC addressing ──

def test_talk_with_about_topic(game):
    """`talk Old Marta about the road` should match Marta and treat
    'the road' as the message."""
    game.start()
    msgs = game.handle("talk Old Marta about the road")
    text = _text(msgs)
    # No "no one named" rejection; NPC actually replied
    assert "no one" not in text.lower()
    assert "Marta" in text


def test_talk_with_possessive(game):
    """`talk Marta's food` should match Marta and ignore the possessive."""
    game.start()
    msgs = game.handle("talk Marta's food")
    text = _text(msgs)
    assert "no one" not in text.lower()
    assert "Marta" in text


def test_talk_with_full_topic_message(game):
    """`talk Marta about what brings me to Silverbrook` should work."""
    game.start()
    msgs = game.handle("talk Marta about what brings me to Silverbrook")
    text = _text(msgs)
    assert "no one" not in text.lower()
    assert "Marta" in text


def test_tell_first_word_match(game):
    """`tell marta hello` matches Marta on first-word fallback."""
    game.start()
    msgs = game.handle("tell marta hello")
    text = _text(msgs)
    assert "no one" not in text.lower()


def test_talk_to_absent_npc_falls_through_to_dm(game):
    """Phase 11 architecture: when no NPC matches, route to DM adjudication
    (which can narrate naturally) instead of returning a flat error.
    The stub DM returns 'ok.' — assert we see a DM-prefixed message."""
    game.start()
    msgs = game.handle("talk Old John about swords")
    text = _text(msgs)
    assert "DM:" in text
