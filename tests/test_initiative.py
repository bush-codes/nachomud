"""Tests for speed-based initiative system."""
from __future__ import annotations

from engine import build_initiative_order, regen_warrior_ap, WARRIOR_AP_REGEN
from models import AgentState, Item, Mob, Room


def _make_agent(name: str, agent_class: str, speed: int, hp: int = 10) -> AgentState:
    return AgentState(
        name=name,
        personality="Test",
        agent_class=agent_class,
        hp=hp,
        max_hp=hp,
        mp=0,
        max_mp=0,
        weapon=Item(name="Sword", slot="weapon", atk=3),
        armor=Item(name="Armor", slot="armor", pdef=1),
        ring=Item(name="Ring", slot="ring"),
        room_id="room_1",
        speed=speed,
    )


# ── build_initiative_order ──


def test_initiative_speed_ordering():
    """Higher speed goes first."""
    warrior = _make_agent("Kael", "Warrior", speed=3)
    rogue = _make_agent("Shade", "Rogue", speed=6)
    mage = _make_agent("Lyria", "Mage", speed=4)
    rooms = {"room_1": Room(id="room_1", name="Test")}

    order = build_initiative_order([warrior, rogue, mage], rooms)
    names = [e.name for e in order]
    assert names == ["Shade", "Lyria", "Kael"]


def test_initiative_agents_before_mobs_on_tie():
    """On same speed, agents go before mobs."""
    agent = _make_agent("Kael", "Warrior", speed=3)
    mob = Mob(name="Goblin", hp=5, max_hp=5, atk=2, speed=3)
    rooms = {"room_1": Room(id="room_1", name="Test", mobs=[mob])}

    order = build_initiative_order([agent], rooms)
    assert order[0].name == "Kael"
    assert order[1].name == "Goblin"


def test_initiative_alphabetical_tiebreak():
    """Same speed, same type → alphabetical."""
    a1 = _make_agent("Zara", "Warrior", speed=3)
    a2 = _make_agent("Aldric", "Paladin", speed=3)
    rooms = {"room_1": Room(id="room_1", name="Test")}

    order = build_initiative_order([a1, a2], rooms)
    names = [e.name for e in order]
    assert names == ["Aldric", "Zara"]


def test_initiative_dead_excluded():
    """Dead agents and dead mobs are excluded."""
    alive = _make_agent("Kael", "Warrior", speed=3)
    dead = _make_agent("Dead", "Warrior", speed=5, hp=0)
    dead.alive = False
    mob_alive = Mob(name="Goblin", hp=5, max_hp=5, atk=2, speed=4)
    mob_dead = Mob(name="Dead Goblin", hp=0, max_hp=5, atk=2, speed=6)
    rooms = {"room_1": Room(id="room_1", name="Test", mobs=[mob_alive, mob_dead])}

    order = build_initiative_order([alive, dead], rooms)
    names = [e.name for e in order]
    assert "Dead" not in names
    assert "Dead Goblin" not in names
    assert names == ["Goblin", "Kael"]


def test_initiative_mobs_from_multiple_rooms():
    """Mobs from all rooms are included."""
    agent = _make_agent("Kael", "Warrior", speed=3)
    mob1 = Mob(name="Goblin A", hp=5, max_hp=5, atk=2, speed=2)
    mob2 = Mob(name="Goblin B", hp=5, max_hp=5, atk=2, speed=4)
    rooms = {
        "room_1": Room(id="room_1", name="Room 1", mobs=[mob1]),
        "room_2": Room(id="room_2", name="Room 2", mobs=[mob2]),
    }

    order = build_initiative_order([agent], rooms)
    names = [e.name for e in order]
    assert names == ["Goblin B", "Kael", "Goblin A"]


def test_initiative_empty_game():
    """No living entities → empty list."""
    rooms = {"room_1": Room(id="room_1", name="Test")}
    order = build_initiative_order([], rooms)
    assert order == []


def test_initiative_mixed_speeds():
    """Full mix of agents and mobs at various speeds."""
    rogue = _make_agent("Shade", "Rogue", speed=6)
    ranger = _make_agent("Finn", "Ranger", speed=5)
    mage = _make_agent("Lyria", "Mage", speed=4)
    warrior = _make_agent("Kael", "Warrior", speed=3)

    fast_mob = Mob(name="Assassin", hp=8, max_hp=8, atk=4, speed=5)
    slow_mob = Mob(name="Zombie", hp=10, max_hp=10, atk=3, speed=1)
    rooms = {"room_1": Room(id="room_1", name="Test", mobs=[fast_mob, slow_mob])}

    order = build_initiative_order([rogue, ranger, mage, warrior], rooms)
    names = [e.name for e in order]
    # Speed 6: Shade, Speed 5: Assassin (mob) and Finn (agent) → agent first then mob,
    # but alphabetically agent Finn < mob Assassin... wait, agents before mobs on tie.
    # Speed 5: Finn (agent) before Assassin (mob)
    # Speed 4: Lyria
    # Speed 3: Kael
    # Speed 1: Zombie
    assert names == ["Shade", "Finn", "Assassin", "Lyria", "Kael", "Zombie"]


# ── regen_warrior_ap ──


def test_regen_warrior_ap():
    """Warriors regenerate AP each tick, capped at max."""
    warrior = _make_agent("Kael", "Warrior", speed=3)
    warrior.ap = 4
    warrior.max_ap = 10

    regen_warrior_ap([warrior])
    assert warrior.ap == 4 + WARRIOR_AP_REGEN  # 4 + 3 = 7


def test_regen_warrior_ap_capped():
    """AP regen doesn't exceed max_ap."""
    warrior = _make_agent("Kael", "Warrior", speed=3)
    warrior.ap = 9
    warrior.max_ap = 10

    regen_warrior_ap([warrior])
    assert warrior.ap == 10  # 9 + 3 = 12 → capped at 10


def test_regen_warrior_ap_not_for_other_classes():
    """Non-warriors don't get AP regen."""
    mage = _make_agent("Lyria", "Mage", speed=4)
    mage.ap = 0
    mage.max_ap = 0

    regen_warrior_ap([mage])
    assert mage.ap == 0


def test_regen_warrior_ap_dead_warrior():
    """Dead warriors don't regenerate AP."""
    warrior = _make_agent("Kael", "Warrior", speed=3)
    warrior.ap = 4
    warrior.max_ap = 10
    warrior.alive = False

    regen_warrior_ap([warrior])
    assert warrior.ap == 4  # unchanged
