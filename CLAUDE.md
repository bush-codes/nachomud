# NachoMUD - Claude Code Context

## What is this?

AI-powered text-based dungeon crawler where LLM-controlled agents cooperate to navigate dungeons, battle monsters, and defeat a final boss. Players select a party of 3 from 6 character classes (Warrior, Paladin, Mage, Cleric, Ranger, Rogue), each with 5 unique abilities. Mobs have their own LLM-driven turns. Supports multiple worlds with different topologies to test agent generalization. Successor to KinchoMUD (2007-2009) which used neuroevolution; this version uses modern LLMs.

## Project Structure

```
nachomud/
├── main.py              # CLI game loop (20 ticks default)
├── engine.py            # Core game logic: create_agents, resolve_action, witness functions, initiative
├── abilities.py         # 24 ability resolvers (registry pattern), damage formulas, buff/debuff application
├── effects.py           # StatusEffect system: apply, tick, modify damage, consume one-shots
├── mob_ai.py            # LLM-driven mob turns: prompt building, action/comm parsing, ability resolution
├── agent.py             # LLM prompting: comm phase, action phase, class-specific dynamic commands, retry
├── combat.py            # Legacy damage resolution (kept for backwards compat)
├── world.py             # Room loading, world listing, sensory context building
├── models.py            # Dataclasses: Item, Mob, NPC, Room, AgentState, GameEvent, StatusEffect
├── config.py            # CLASS_DEFINITIONS (6 classes), ABILITY_DEFINITIONS (24 abilities), LLM settings
├── memory.py            # (unused — memory system disabled, to be rethought)
├── llm.py               # LLM abstraction (Anthropic SDK or Ollama)
├── narrator.py          # Story narration via LLM (room descriptions, combat flavor)
├── data/
│   ├── worlds/          # World JSON files (one per dungeon)
│   │   ├── shadowfell.json    # 15-room linear fortress (original)
│   │   ├── frostpeak.json     # 13-room hub-and-spoke frozen citadel
│   │   ├── serpentmire.json   # 12-room ring/loop swamp
│   │   └── emberhollows.json  # 14-room wide branching volcanic caverns
│   ├── world.json       # Legacy fallback (kept for backwards compat)
│   ├── memories/        # Per-agent JSON (regenerated each run)
│   └── logs/            # Simulation transcripts (auto-generated)
├── tests/               # pytest test suite (224 tests)
│   ├── conftest.py      # Shared fixtures: mock_room, mock_agent, mock_mob, mock_llm
│   ├── test_abilities.py    # All 24 abilities + edge cases
│   ├── test_effects.py      # StatusEffect system: apply, tick, modify, consume
│   ├── test_engine.py       # Engine functions: resolve_action, witnesses, create_agents
│   ├── test_initiative.py   # Speed ordering, tiebreaks, AP regen
│   ├── test_mob_ai.py       # Mob prompt building, parsing, ability resolution
│   ├── test_equipment.py    # Class restrictions, equip logic
│   ├── test_combat.py       # Legacy combat functions
│   ├── test_agent.py        # Action parsing, validation, command building
│   └── test_world_data.py   # World JSON validation (all 4 worlds)
├── web/
│   ├── backend/
│   │   └── server.py    # FastAPI server - streams simulation as NDJSON
│   └── frontend/        # React 19 + TypeScript + Vite 6 + Tailwind CSS
│       └── src/
│           ├── App.tsx           # Main component: streaming state management, party selection
│           ├── types.ts          # TS interfaces, CLASS_COLORS, getAgentColor()
│           └── components/
│               ├── GameHeader.tsx    # Status badge, World/Model selectors, Run/Reset
│               ├── DungeonMap.tsx    # SVG map with auto-layout, agent dots, room states
│               ├── AgentPanel.tsx    # HP/MP/AP bars, status effects, equipment, class colors
│               ├── EventLog.tsx      # Color-coded live event stream (agents + mobs)
│               └── PartySelector.tsx # 6-class party picker (max 3)
└── neatMUD/             # Legacy: original KinchoMUD C++ + rtNEAT (archival)
```

## How to Run

### Web mode (primary)
```bash
# Terminal 1: Backend (from project root)
source .venv/bin/activate
uvicorn web.backend.server:app --host 0.0.0.0 --port 4000

# Terminal 2: Frontend dev server
cd web/frontend
npm run dev
# → http://localhost:5173 (proxies /api/* to :4000)
```

Or use `./run.sh` which starts Ollama + backend + frontend together.

### CLI mode
```bash
source .venv/bin/activate
python main.py
```

### Run tests
```bash
source .venv/bin/activate
pytest tests/          # All 224 tests
pytest tests/ -x       # Stop at first failure
pytest tests/ -v       # Verbose output
```

### Build frontend for production
```bash
cd web/frontend
npm run build    # tsc && vite build → dist/
```
FastAPI serves the built frontend from `web/frontend/dist/` automatically.

### Environment
- `LLM_BACKEND=ollama` (default) or `LLM_BACKEND=anthropic`
- `ANTHROPIC_API_KEY=sk-...` (required when using anthropic backend)

## Architecture: 6 Character Classes

Players select a party of 3 from 6 classes. Each class has unique abilities, stats, and a resource system.

| Class | HP | Resource | Speed | Abilities |
|-------|-----|----------|-------|-----------|
| Warrior | 25 | AP:10 | 3 | attack, cleave, taunt, defend, rally |
| Paladin | 20 | MP:8 | 3 | attack, smite, lay_on_hands, shield, consecrate |
| Mage | 8 | MP:25 | 4 | attack, missile, arcane_storm, curse, barrier |
| Cleric | 14 | MP:18 | 3 | attack, heal, ward, holy_bolt, cure |
| Ranger | 14 | MP:10 | 5 | attack, aimed_shot, volley, poison_arrow, sleep |
| Rogue | 12 | MP:8 | 6 | attack, backstab, bleed, evade, smoke_bomb |

**Key design:**
- Zero ability overlap between classes (except shared `attack`)
- Warrior uses AP (regenerates 3/tick). All others use MP. Rogue uses HP for backstab/evade, MP for bleed/smoke_bomb
- All combat is deterministic (no hit chance/RNG)
- Defined in `config.py` as `CLASS_DEFINITIONS` and `ABILITY_DEFINITIONS`

## Architecture: Ability System (`abilities.py`)

Registry pattern: `ABILITY_REGISTRY[name] = resolver_function`. Each ability has a resolver that checks cost, finds targets, pays cost, applies effects, and returns `GameEvent`s.

`resolve_ability(source, ability_name, target_name, room, tick, agents, rooms)` dispatches to the right resolver.

**Damage formulas:**
| Ability | Formula |
|---------|---------|
| attack | `weapon.atk - target.pdef` (min 1) |
| cleave | same per mob, AoE, 3 AP |
| smite | `floor(weapon.atk * 1.5) - target.mdef` (min 1), 2 MP |
| consecrate | `weapon.atk - target.mdef` (min 1) per mob, 4 MP |
| missile | `ring.mdmg - target.mdef` (min 1), 1 MP |
| arcane_storm | `ring.mdmg * 2 - target.mdef` (min 1) per mob, 4 MP |
| holy_bolt | `floor(ring.mdmg * 1.5) - target.mdef` (min 1), 2 MP |
| aimed_shot | `weapon.atk * 2 - target.pdef` (min 1), 3 MP |
| volley | `weapon.atk - target.pdef` (min 1) per mob, 3 MP |
| backstab | `floor(weapon.atk * 2.5)` (ignores defense), 3 HP |

**Buff/debuff values:**
| Ability | Effect | Value | Duration |
|---------|--------|-------|----------|
| taunt | taunted (all mobs) | — | 1 tick |
| defend | defending (self) | 50% reduction | 1 tick |
| rally | rallied (all allies) | +2 damage | 1 use |
| ward | warded (target) | -3 damage | 3 ticks |
| barrier | barrier (target) | 8 HP absorb | until depleted |
| shield | shielded (target) | redirect to Paladin | 1 hit |
| evade | evading (self) | 0 damage | 1 hit |
| sleep | asleep (target) | skip turn | 2 ticks |
| smoke_bomb | blinded (all mobs) | -3 damage | 2 ticks |
| curse | cursed | 2 dmg/tick | 3 ticks |
| poison_arrow | poisoned | 2 dmg/tick | 3 ticks |
| bleed | bleeding | 2 dmg/tick | 3 ticks |
| heal | — | 30% max HP | — |
| lay_on_hands | — | 40% max HP | — |
| cure | — | remove all debuffs | — |

## Architecture: StatusEffect System (`effects.py`)

Generic buff/debuff system. `StatusEffect` dataclass: `name`, `source`, `remaining_ticks`, `value`.

**Functions:**
- `apply_effect(target, effect)` — apply, refresh (don't stack) if exists
- `tick_effects(target, tick)` → list[GameEvent] — process DoTs, decrement, remove expired
- `modify_incoming_damage(target, raw_damage)` → int — evade→defend→ward→barrier chain
- `modify_outgoing_damage(source, raw_damage)` → int — rally (+2, consumed)
- `modify_source_damage(source, raw_damage)` → int — blinded (-3)
- `consume_effect(target, name)` — for one-shot effects (evade, shield)
- `clear_debuffs(target)` — for cure ability
- `is_incapacitated(target)` — checks asleep

**Effect categories:**
- Buffs (beneficial): defending, warded, rallied, barrier, evading, shielded
- Debuffs (harmful): taunted, cursed, poisoned, bleeding, asleep, blinded

## Architecture: Speed-Based Initiative

`build_initiative_order(agents, rooms)` in `engine.py` collects all living agents + living mobs, sorts by speed descending. Ties: agents before mobs, then alphabetical.

**Each tick:**
1. Comm phase: agents communicate in speed order
2. Mob comm phase: bosses always talk, regular mobs 30% chance
3. Action phase: all entities (agents + mobs) act in interleaved speed order
4. Effect ticks: DoTs damage, durations decrement, expired effects removed
5. AP regen: Warriors gain +3 AP/tick (capped at max)
6. Win/loss check: boss dead = victory, all agents dead = defeat

## Architecture: Mob AI (`mob_ai.py`)

Mobs have their own LLM-driven turns instead of just counterattacking.

- `build_mob_action_prompt(mob, room, agents_here)` — simpler than agent prompt: mob stats, enemies (agents), abilities
- `get_mob_action(mob, room, agents, rooms, tick)` → (ability, target). Fallback: attack random agent
- `get_mob_comm(mob, room, agents)` → optional string. Bosses always comm, regular mobs 30% chance
- `resolve_mob_ability(mob, ability, target, room, tick, agents)` — dispatches to mob-specific resolvers

**Enforcement:**
- Taunt: if taunted, override LLM target to be the taunter
- Sleep: skip turn entirely if asleep
- Bosses don't move; regular mobs currently don't move either (future: move toward nearest occupied room)

**Mob ability types:** attack, curse, poison_arrow, bleed, sleep, heal, cleave (AoE), plus any ability from `ABILITY_DEFINITIONS` via target type dispatch.

**World JSON mob format:**
```json
{"name": "Goblin Shaman", "hp": 8, "max_hp": 8, "atk": 3, "pdef": 1, "mdef": 2,
 "speed": 4, "abilities": ["attack", "curse", "heal"],
 "personality": "Cunning shaman that curses the strongest foe.", "is_boss": false}
```

## Architecture: Multi-World System

Worlds are stored as JSON files in `data/worlds/`. Each file has a `meta` block and a `rooms` array:

```json
{
  "meta": { "name": "Display Name", "description": "Short description" },
  "rooms": [ ... ]
}
```

**Available worlds:**
- `shadowfell` — Linear fortress with side branches (15 rooms, boss: Void Lord Malachar)
- `frostpeak` — Hub-and-spoke frozen citadel with 3 wings (13 rooms, boss: Frost Titan Valdris)
- `serpentmire` — Ring/loop swamp with multiple paths to boss (12 rooms, boss: Naga Sorceress Ssythara)
- `emberhollows` — Wide branching volcanic caverns with dead-end treasure rooms (14 rooms, boss: Magma Drake Pyraxis)

**Backend:**
- `world.py`: `list_worlds()` scans `data/worlds/*.json`, `build_world(world_id)` loads a specific world
- `server.py`: `GET /api/worlds` lists worlds, `GET /api/world?world_id=X` loads one, `GET /api/classes` returns class definitions, `POST /api/simulate?world_id=X&party=Warrior,Mage,Cleric` runs with it

**Frontend:**
- World selector dropdown in `GameHeader.tsx`, disabled during simulation
- `PartySelector.tsx` — grid of 6 class cards, click to toggle, max 3
- `DungeonMap.tsx` uses BFS auto-layout (`computeRoomPositions`) — no hardcoded positions
- World rooms reload when selection changes

## Architecture: Game Loop

**Each tick (up to MAX_TICKS=20):**
1. **Communication phase** — agents in speed order (sequential, so later agents see earlier comms):
   a. Build sensory context + witnessed events
   b. LLM call with Think/Comm format — agent decides whether to say/tell/whisper/yell or stay silent
   c. Only ally communication allowed (no NPC tells) — invalid comms are silently skipped
   d. Resolved comms are witnessed by relevant agents before the action phase begins
2. **Mob communication phase** — bosses always speak, regular mobs 30% chance
3. **Action phase** — all entities (agents + mobs) in speed order:
   a. If agent: build sensory context, get LLM action, validate, resolve, witness
   b. If mob: get LLM action (with taunt/sleep enforcement), resolve, witness
4. **Effect ticks** — DoTs damage all agents and mobs, durations decrement, expired effects removed
5. **AP regeneration** — Warriors gain +3 AP/tick (capped at max)
6. **Win/loss check** — boss dead = victory, all agents dead = defeat

## Architecture: Engine (`engine.py`)

Central game logic module. Eliminates duplication between `main.py` and `server.py`.

**Key functions:**
- `create_agents(party, rooms)` — creates agents from CLASS_DEFINITIONS based on party list
- `resolve_action(agent, cmd, arg, ...)` — dispatches movement, combat (→ `abilities.py`), items, communication
- `build_initiative_order(agents, rooms)` — speed-based turn ordering for agents + mobs
- `regen_warrior_ap(agents)` — +3 AP/tick for living Warriors
- `equip_item(agent, item)` — auto-equip if better stats, respects class restrictions
- `can_equip(agent, item)` — checks `item.allowed_classes`
- `check_boss_defeated(rooms)`, `all_agents_dead(agents)` — win/loss conditions
- `witness_action()`, `witness_comm()`, `witness_private()`, `witness_yell()` — event routing

## Architecture: Witnessed Events (MUD Scrollback)

Agents only know what they've personally witnessed — like a real MUD player's scrollback. Events are routed to **three separate history categories**, each with its own rolling window, so different types of information never crowd each other out:

### Three-Category History

| Category | Field | Cap | What goes in | Prompt section |
|---|---|---|---|---|
| **Action** | `action_history` | 12 | Combat, movement, items, arrivals/departures, effect ticks, mob actions | `=== RECENT EVENTS ===` |
| **Comm** | `comm_history` | 5 | tell (ally), say, whisper, yell, mob taunts | `=== ALLY COMMUNICATIONS ===` |
| **Lore** | `lore_history` | 3 | NPC dialogue (summarized) | `=== NPC LORE ===` |

**Why three categories:** A flat history list lets NPC atmospheric dialogue and yell amplification loops flood out tactical information (combat, movement). By separating categories, tactical events can never be crowded out by chatter, and NPC lore stays as persistent reference context without dominating the prompt.

**Event routing:** Each `GameEvent` has a `category` field (`"action"`, `"comm"`, `"lore"`) set at creation time in `resolve_action()` based on who the target is (NPC tell → lore, agent tell → comm, combat → action). Special cases: whispers use `_witness_private()` (always comm), yells use `_witness_yell()` (always comm).

### Visibility rules
- **Your own actions** prefixed with `>>` (e.g., `>> attack Goblin Guard → Kael attacks Goblin Guard for 5 damage.`)
- **Others' actions in your room** (e.g., `Lyria casts arcane storm! Goblin Scout SLAIN!`)
- **Mob actions in your room** (e.g., `Goblin Shaman curses Kael!`)
- **Arrivals/departures** (e.g., `Finn leaves heading north`, `Kael arrives from the south`)
- **Whispers** — private, only sender (with `>>`) and target see it; other agents in the room do not
- **Yells** — broadcast via BFS up to 3 rooms: same room sees `Kael yells: "Help!"`, adjacent (1 hop) sees `Kael yells from the south (Great Hall): "Help!"`, 2-3 hops sees `Kael yells in the distance: "Help!"`
- **NPC dialogue** — long narrator-generated dialogue is LLM-summarized to 1-2 sentences before entering `lore_history` (full text still shown in event log)
- **No cross-room information** — if an ally moves away, you don't see what they do next (except yells)

## Architecture: Action Validation & Retry

When an agent produces an invalid action (e.g., using an ability they don't have, attacking an NPC):
1. The action is validated against the current game state and agent's class abilities
2. A dynamic list of valid actions is generated (only showing what's actually possible)
3. The model is re-prompted: "Your action was invalid. Evaluate each option, then choose."
4. Up to 2 retries; forces deliberation over real options instead of pattern-matching

## Architecture: Class-Specific Equipment

Items can have `allowed_classes: ["Warrior", "Paladin"]` to restrict who can equip them.

- `can_equip(agent, item)` in `engine.py` checks `item.allowed_classes` before equipping
- `build_sensory_context` in `world.py` shows `[CANNOT USE]` for wrong-class items
- Rings remain unrestricted
- Class restriction is optional — items without `allowed_classes` can be used by anyone

## Architecture: Streaming Protocol

`POST /api/simulate?world_id=shadowfell&party=Warrior,Mage,Ranger` returns newline-delimited JSON:

```
{"type": "init", "world": {...}, "agents": [...]}
{"type": "event", "tick": 1, "event": {...}, "agent_states": [...], "room_states": {...}}
{"type": "event", "tick": 1, "event": {...}, "agent_states": [...], "room_states": {...}}
{"type": "tick", "tick": 1, "events": [...], "agent_states": [...], "room_states": {...}}
...
{"type": "done", "outcome": "victory", "total_ticks": 15}
```

- `event` messages stream live as each agent/mob acts — frontend updates immediately
- `event` messages include `agent_states` and `room_states` so the UI updates agent panels and dungeon map in real-time
- `agent_states` include `agent_class`, `ap`, `max_ap`, `speed`, `status_effects`
- `tick` messages are end-of-tick snapshots (belt-and-suspenders state sync)
- Frontend accumulates all events into a flat `allEvents` array — no tick-based grouping in the UI

## Frontend State Model

The UI is a continuous live event stream (no tick slider/playback controls):

- `allEvents: GameEventData[]` — every event across the entire simulation
- `latestAgentStates: AgentSnapshot[]` — updated on each event message
- `latestRoomStates: Record<string, RoomSnapshot>` — updated on each event message
- `simulation: SimulationResult` — outcome, world definition, agent info
- `party: string[]` — selected party classes (default: ["Warrior", "Mage", "Ranger"])
- `classDefinitions: Record<string, ClassDefinition>` — fetched from `/api/classes`

`SimulationResult` does NOT contain ticks or per-tick event arrays. The `TickData` type was removed.

## Frontend: Class-Based Colors

Colors are defined by class, not agent name. `CLASS_COLORS` in `types.ts`:

| Class | Color | Primary Hex |
|-------|-------|------------|
| Warrior | Red | `#ef4444` |
| Paladin | Amber | `#f59e0b` |
| Mage | Blue | `#3b82f6` |
| Cleric | Gray | `#9ca3af` |
| Ranger | Green | `#22c55e` |
| Rogue | Purple | `#a855f7` |

`getAgentColor(agent)` prefers `agent_class` lookup, falls back to name-based `AGENT_COLORS` (maps default names like Kael → Warrior colors).

Used in: `DungeonMap.tsx` (agent dots), `AgentPanel.tsx` (cards, bars), `EventLog.tsx` (agent name colors), `PartySelector.tsx` (selection highlight).

## Key Game Mechanics

- **Physical combat:** `weapon.atk - target.pdef` (min 1). Each class has unique damage abilities.
- **Magic combat:** `ring.mdmg * multiplier - target.mdef`. Multiple AoE and single-target options.
- **Healing:** Cleric heals 30% max HP (2 MP). Paladin heals 40% (3 MP).
- **DoTs:** Curse, poison_arrow, bleed all deal 2 dmg/tick for 3 ticks.
- **Defensive buffs:** Defend (50% reduction), ward (-3 dmg), barrier (absorb 8), evade (negate 1 hit), shield (redirect to Paladin).
- **CC:** Sleep (skip 2 turns), taunt (force target), smoke bomb (-3 dmg for 2 ticks).
- **Item equip:** Auto-equip if better stats (ATK for weapon, PDEF for armor, MDMG for ring). Class restrictions apply.
- **Mob turns:** Mobs act on their own initiative using LLM-driven decisions. Taunt and sleep are enforced.
- **Sensory context:** Agents see current room contents (with item stats and class restrictions) + exit names + visited rooms.
- **Communication:** 4 commands with different scopes — `tell` (room, targeted), `say` (room, broadcast), `whisper` (private), `yell` (multi-room, BFS up to 3 hops).
- **Target rules:** Enemies → damage/debuff abilities. Allies → heal/buff abilities. NPCs → tell only. Items → get only.

## Agent Prompt Design

**North star: Agents should reason, not follow rules.** The whole point of using LLMs is emergent behavior — if we're writing conditional warnings and behavioral nudges into prompts, we're just building a scripted game with extra steps. Give the model the game state and let it figure out what to do. The dynamic commands list prevents impossible actions; everything else is the model's job.

- **Action prompt essentials:** Identity + personality + class, quest, equipment/stats (HP/MP/AP), three-category history, sensory context (with item stats/restrictions and visited rooms), class-specific dynamic commands, Think/Do format.
- **Comm prompt essentials:** Identity + personality, stats, sensory context, three-category history, available comm commands, Think/Comm format.
- **Class-specific commands:** `_build_commands_help()` in `agent.py` looks up agent's class → only shows that class's abilities with correct costs. This prevents impossible actions.
- **Information-first design:** Instead of rules ("don't heal at full HP"), give the model information it can reason from.
- **Dynamic quest text:** `config.QUEST_DESCRIPTION` is set at runtime from each world's `meta.description`.
- **Multi-line Think parsing:** `_parse_think_do()` and `_parse_think_comm()` capture everything between `Think:` and `Do:`/`Comm:` as reasoning, even across multiple lines.
- **NPC dialogue summarization:** Full narrator-generated NPC dialogue is shown in the event log, but an LLM-summarized 1-2 sentence version goes into agent `lore_history`.
- **BASE_PERSONALITY** (in `config.py`): Shared personality emphasizing exploration, combat for loot, NPC interaction, and ally coordination.
- **Free communication phase:** Each tick starts with a communication phase where agents can say/tell/whisper/yell without consuming their action.

## Common Tasks

- **Add a new class:** Add to `CLASS_DEFINITIONS` in `config.py`, add abilities to `ABILITY_DEFINITIONS`, add resolvers to `abilities.py` `ABILITY_REGISTRY`, add color to `CLASS_COLORS` in `types.ts`
- **Add an ability:** Add to `ABILITY_DEFINITIONS` in `config.py`, create resolver in `abilities.py`, add to class's abilities list
- **Add a mob ability:** If it maps to an existing ability type, it works via `resolve_mob_ability` dispatch. For new types, add a resolver in `mob_ai.py`
- **Add a new world:** Create `data/worlds/yourworld.json` with `meta` + `rooms` (see existing files for format). Include speed/abilities/personality/pdef on all mobs. It auto-appears in the UI.
- **Add rooms to a world:** Edit the world's JSON in `data/worlds/`. Ensure bidirectional exits.
- **Change LLM model:** Edit `llm.py` model parameter or `config.py` defaults
- **Frontend component:** All in `web/frontend/src/components/`, styled with Tailwind utility classes

## Working on This Project

- **Always update this file (CLAUDE.md)** when making changes that affect architecture, game mechanics, prompt structure, file responsibilities, or anything documented here. This is the source of truth for how the project works.
- **Always update README.md** when making changes that affect user-facing behavior: game mechanics, how to run, features, project structure, configuration, or anything a new reader would need to know.
- **Hardcore testing required.** Write tests as you go. Tests must pass before moving on. This project has a lot of interacting systems (combat, abilities, initiative, effects, validation, witnessing, mob AI) and changes can break things in subtle ways. Run `pytest tests/` frequently. Use `pytest tests/ -x` to stop at first failure during development.

## Things That No Longer Exist

- `TickControls.tsx` — deleted (no tick slider/playback)
- `TickData` interface — removed from `types.ts`
- `ticks` array on `SimulationResult` — removed
- Per-tick state in App.tsx (`playing`, `liveFollow`, `speed`, `liveTick`) — all removed
- `memory.py` — disabled (to be rethought)
- Post-action comments — removed (was causing bad advice cascades between agents)
- Global `last_tick_recap` / `actions_so_far` — replaced by room-scoped three-category witnessed events
- Single flat `action_history` — split into three categories: `action_history`, `comm_history`, `lore_history`
- Round 0 planning discussion — replaced by per-tick communication phase
- `build_discussion_prompt` / `get_agent_discussion` — removed with round 0
- Static `COMMANDS_HELP` — replaced by `_build_commands_help()` which generates class-specific dynamic commands
- Mob counterattack system — replaced by LLM-driven mob turns (`mob_ai.py`)
- Hardcoded 3-agent party — replaced by party selection from 6 classes
- Name-based agent colors — replaced by class-based `CLASS_COLORS` with `getAgentColor()` helper
- `SPELL_COSTS` as primary ability cost source — replaced by `ABILITY_DEFINITIONS` (SPELL_COSTS kept for legacy compat)
- `tick_poison` — replaced by generic `tick_effects` from `effects.py`
