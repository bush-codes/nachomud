from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class Item:
    name: str
    slot: str  # weapon, armor, ring
    atk: int = 0
    pdef: int = 0
    mdef: int = 0
    mdmg: int = 0


@dataclass
class Mob:
    name: str
    hp: int
    max_hp: int
    atk: int
    description: str = ""
    loot: list[Item] = field(default_factory=list)
    poison_remaining: int = 0
    mdef: int = 0
    is_boss: bool = False


@dataclass
class NPC:
    name: str
    title: str
    dialogue: list[str] = field(default_factory=list)
    item: Item | None = None
    item_given: bool = False


@dataclass
class Room:
    id: str
    name: str
    description: str = ""
    exits: dict[str, str] = field(default_factory=dict)  # direction -> room_id
    mobs: list[Mob] = field(default_factory=list)
    npcs: list[NPC] = field(default_factory=list)
    items: list[Item] = field(default_factory=list)
    visited: bool = False


@dataclass
class AgentState:
    name: str
    personality: str
    agent_class: str
    hp: int
    max_hp: int
    mp: int
    max_mp: int
    weapon: Item
    armor: Item
    ring: Item
    room_id: str = ""
    alive: bool = True
    inventory: list[Item] = field(default_factory=list)
    last_action: str = ""
    last_result: str = ""


@dataclass
class GameEvent:
    tick: int
    agent: str
    action: str
    result: str
    room_id: str
