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
    slot: str  # weapon, armor, shield, ring, consumable

    # Weapon fields (5e-style)
    damage_die: str = ""        # e.g. "1d8". Empty = non-weapon.
    damage_type: str = "slashing"  # slashing, piercing, bludgeoning, fire, radiant, etc.
    finesse: bool = False        # weapon may use DEX mod instead of STR
    ranged: bool = False         # ranged attack (uses DEX)
    versatile_die: str = ""      # alternate die when wielded two-handed (e.g. "1d10")
    is_two_handed: bool = False  # requires two hands

    # Armor fields
    armor_base: int = 0          # base AC value (e.g. 16 for chainmail)
    armor_max_dex: int | None = None  # cap on DEX bonus (heavy=0, medium=2, light=None)

    # Shield fields
    shield_bonus: int = 0        # +2 typical

    # Generic enchantment / ring bonuses
    ac_bonus: int = 0
    attack_bonus_bonus: int = 0  # +N to attack rolls
    damage_bonus: int = 0        # +N to damage rolls
    save_bonus: int = 0
    spell_attack_bonus: int = 0
    spell_dc_bonus: int = 0

    # Class restrictions
    allowed_classes: list[str] | None = None

    # Legacy fields (transitional — will be removed once all callers migrate)
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
    loot: list[Item] = field(default_factory=list)
    mdef: int = 0
    pdef: int = 0
    is_boss: bool = False
    speed: int = 3
    abilities: list[str] = field(default_factory=lambda: ["attack"])
    personality: str = ""
    room_id: str = ""
    alive: bool = True
    status_effects: list[StatusEffect] = field(default_factory=list)

    # 5e additions
    stats: dict[str, int] = field(default_factory=dict)  # STR/DEX/CON/INT/WIS/CHA
    level: int = 1
    proficiency_bonus: int = 2
    ac: int = 10
    damage_die: str = "1d4"      # default natural attack die
    damage_bonus: int = 0
    challenge_rating: float = 0.25  # XP scale
    xp_value: int = 50

    # Mobility / faction
    faction: str = "wild_beast"
    aggression: int = 5            # 0-10
    home_room: str = ""
    current_room: str = ""
    wander_radius: int = 2
    zone_tag: str = ""
    ai_state: str = "idle"         # idle | wander | pursue | return
    ai_target: str = ""             # player_id or last-known direction

    # Identity
    mob_id: str = ""
    kind: str = ""


@dataclass
class NPC:
    name: str
    title: str
    dialogue: list[str] = field(default_factory=list)
    item: Item | None = None
    item_given: bool = False
    interactions_left: int = 3  # set randomly 1-5 at world load
    personality: str = ""

    # Routine: list of (start_hr, end_hr, location_id, activity_blurb)
    routines: list[dict] = field(default_factory=list)
    npc_id: str = ""
    faction: str = "none"

    # Shop wares: list of {name, slot, price, ...} dicts. The dict is passed
    # straight to Item(**wares) when minted into the player's inventory, with
    # `price` stripped first.
    wares: list[dict] = field(default_factory=list)

    # Lore facts this NPC can dispense — small bullet list of things they
    # know about the world (rumors, history, what's nearby). The NPC LLM
    # picks one untold fact per conversation turn instead of generic
    # greetings; the NPC chat history tells it which it has already shared.
    lore: list[str] = field(default_factory=list)


@dataclass
class Room:
    id: str
    name: str
    description: str = ""
    exits: dict[str, str] = field(default_factory=dict)  # direction -> room_id
    mobs: list[Mob] = field(default_factory=list)        # transitional; canonical store is mobs.json
    npcs: list[NPC] = field(default_factory=list)
    items: list[Item] = field(default_factory=list)      # transitional; canonical store is items.json
    visited: bool = False

    # Player-mode additions
    zone_tag: str = ""
    flags: dict[str, bool] = field(default_factory=dict)


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
    action_history: list[str] = field(default_factory=list)
    comm_history: list[str] = field(default_factory=list)
    lore_history: list[str] = field(default_factory=list)
    visited_rooms: list[str] = field(default_factory=list)
    last_seen: dict[str, str] = field(default_factory=dict)
    ap: int = 0
    max_ap: int = 0
    speed: int = 3
    status_effects: list[StatusEffect] = field(default_factory=list)

    # 5e additions
    stats: dict[str, int] = field(default_factory=dict)  # STR/DEX/CON/INT/WIS/CHA
    race: str = "Human"
    level: int = 1
    xp: int = 0
    proficiency_bonus: int = 2
    hit_die: int = 8                     # d8 default
    ac: int = 10
    shield: Item | None = None           # optional shield slot
    save_proficiencies: list[str] = field(default_factory=list)  # ["STR", "CON"]
    abilities: list[str] = field(default_factory=list)            # unlocked abilities for this class+level

    # Player-mode additions
    player_id: str = ""
    respawn_room: str = ""
    world_id: str = "default"
    game_clock: dict = field(default_factory=lambda: {"day": 1, "minute": 480})  # day 1, 8am
    dm_context: dict = field(default_factory=lambda: {"recent_exchanges": [], "summary": "", "pending_hints": []})
    gold: int = 0


@dataclass
class GameEvent:
    tick: int
    agent: str
    action: str
    result: str
    room_id: str
    witness_text: str = ""
    category: str = "action"  # "action" | "comm" | "lore"
