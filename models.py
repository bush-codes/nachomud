from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class StatusEffect:
    name: str           # e.g., "defending", "poisoned", "warded"
    source: str         # who applied it (agent/mob name)
    remaining_ticks: int  # -1 = until consumed (one-shot effects)
    value: int = 0      # effect-specific: damage amount, reduction amount, absorb HP, etc.


@dataclass
class Item:
    name: str
    slot: str  # weapon, armor, ring
    atk: int = 0
    pdef: int = 0
    mdef: int = 0
    mdmg: int = 0
    allowed_classes: list[str] | None = None  # None = any class can use


@dataclass
class Mob:
    name: str
    hp: int
    max_hp: int
    atk: int
    description: str = ""
    loot: list[Item] = field(default_factory=list)
    poison_remaining: int = 0  # legacy — will be replaced by StatusEffect system
    mdef: int = 0
    pdef: int = 0
    is_boss: bool = False
    speed: int = 3
    abilities: list[str] = field(default_factory=lambda: ["attack"])
    personality: str = ""
    room_id: str = ""
    alive: bool = True
    status_effects: list[StatusEffect] = field(default_factory=list)


@dataclass
class NPC:
    name: str
    title: str
    dialogue: list[str] = field(default_factory=list)
    item: Item | None = None
    item_given: bool = False
    interactions_left: int = 3  # set randomly 1-5 at world load
    speed: int = 0
    room_id: str = ""
    personality: str = ""


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
    action_history: list[str] = field(default_factory=list)  # tactical events: combat, movement, items
    comm_history: list[str] = field(default_factory=list)    # ally communications: tell, say, whisper, yell
    lore_history: list[str] = field(default_factory=list)    # NPC dialogue summaries
    visited_rooms: list[str] = field(default_factory=list)   # room names in order of first visit
    ap: int = 0       # action points (Warrior resource)
    max_ap: int = 0
    speed: int = 3
    status_effects: list[StatusEffect] = field(default_factory=list)


@dataclass
class GameEvent:
    tick: int
    agent: str
    action: str
    result: str
    room_id: str
    witness_text: str = ""  # shortened version for action_history (e.g., summarized NPC dialogue)
    category: str = "action"  # "action" (combat/movement/items), "comm" (ally talk), "lore" (NPC dialogue)
