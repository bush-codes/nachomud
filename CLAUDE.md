# NachoMUD - Claude Code Context

## What is this?

AI-powered text-based dungeon crawler where 3 LLM-controlled agents (Kael the Warrior, Lyria the Mage, Finn the Ranger) cooperate to navigate dungeons, battle monsters, and defeat a final boss. Supports multiple worlds with different topologies to test agent generalization. Successor to KinchoMUD (2007-2009) which used neuroevolution; this version uses modern LLMs.

## Project Structure

```
nachomud/
├── main.py              # CLI game loop (20 ticks default)
├── agent.py             # LLM prompting: round-0 planning, action phase, retry validation
├── combat.py            # Damage resolution: attack, missile, fireball, poison, heal
├── world.py             # Room loading, world listing, sensory context building
├── models.py            # Dataclasses: Item, Mob, NPC, Room, AgentState, GameEvent
├── config.py            # Agent templates (3 agents), spell costs, LLM_BACKEND, MAX_TICKS
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
├── web/
│   ├── backend/
│   │   └── server.py    # FastAPI server - streams simulation as NDJSON
│   └── frontend/        # React 19 + TypeScript + Vite 6 + Tailwind CSS
│       └── src/
│           ├── App.tsx           # Main component: streaming state management
│           ├── types.ts          # TS interfaces matching backend models
│           └── components/
│               ├── GameHeader.tsx   # Status badge, World/Model selectors, Run/Reset
│               ├── DungeonMap.tsx   # SVG map with auto-layout, agent dots, room states
│               ├── AgentPanel.tsx   # HP/MP bars, equipment, last action
│               └── EventLog.tsx     # Color-coded live event stream
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

### Build frontend for production
```bash
cd web/frontend
npm run build    # tsc && vite build → dist/
```
FastAPI serves the built frontend from `web/frontend/dist/` automatically.

### Environment
- `LLM_BACKEND=ollama` (default) or `LLM_BACKEND=anthropic`
- `ANTHROPIC_API_KEY=sk-...` (required when using anthropic backend)

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
- `server.py`: `GET /api/worlds` lists worlds, `GET /api/world?world_id=X` loads one, `POST /api/simulate?world_id=X` runs with it

**Frontend:**
- World selector dropdown in `GameHeader.tsx`, disabled during simulation
- `DungeonMap.tsx` uses BFS auto-layout (`computeRoomPositions`) — no hardcoded positions
- World rooms reload when selection changes

## Architecture: Game Loop

**Each tick (up to MAX_TICKS=20):**
1. **Communication phase** — for each agent (sequential, so later agents see earlier comms):
   a. Build sensory context + witnessed events
   b. LLM call with Think/Comm format — agent decides whether to say/tell/whisper/yell or stay silent
   c. Only ally communication allowed (no NPC tells) — invalid comms are silently skipped
   d. Resolved comms are witnessed by relevant agents before the action phase begins
2. **Action phase** — for each agent:
   a. Build sensory context + witnessed events (now includes this tick's comms)
   b. Get action from LLM using Think/Do chain-of-thought format with dynamic commands (only shows actions possible in current state)
   c. Validate action — if invalid, retry up to 2 times with a dynamic valid-actions list
   d. Resolve action → witnessed by all agents in the same room (room-scoped, not global)
   e. Movement: departure room sees "X leaves heading north", arrival room sees "X arrives from the south"
3. **Poison tick** — apply poison damage to affected mobs
4. **Win/loss check** — boss dead = victory, all agents dead = defeat

## Architecture: Witnessed Events (MUD Scrollback)

Agents only know what they've personally witnessed — like a real MUD player's scrollback. Events are routed to **three separate history categories**, each with its own rolling window, so different types of information never crowd each other out:

### Three-Category History

| Category | Field | Cap | What goes in | Prompt section |
|---|---|---|---|---|
| **Action** | `action_history` | 12 | Combat, movement, items, arrivals/departures, poison | `=== RECENT EVENTS ===` |
| **Comm** | `comm_history` | 5 | tell (ally), say, whisper, yell | `=== ALLY COMMUNICATIONS ===` |
| **Lore** | `lore_history` | 3 | NPC dialogue (summarized) | `=== NPC LORE ===` |

**Why three categories:** A flat history list lets NPC atmospheric dialogue and yell amplification loops flood out tactical information (combat, movement). By separating categories, tactical events can never be crowded out by chatter, and NPC lore stays as persistent reference context without dominating the prompt.

**Event routing:** Each `GameEvent` has a `category` field (`"action"`, `"comm"`, `"lore"`) set at creation time in `resolve_action()` based on who the target is (NPC tell → lore, agent tell → comm, combat → action). Special cases: whispers use `_witness_private()` (always comm), yells use `_witness_yell()` (always comm).

### Visibility rules
- **Your own actions** prefixed with `>>` (e.g., `>> attack Goblin Guard → Kael attacks Goblin Guard for 5 damage.`)
- **Others' actions in your room** (e.g., `Lyria casts fireball! Goblin Scout SLAIN!`)
- **Arrivals/departures** (e.g., `Finn leaves heading north`, `Kael arrives from the south`)
- **Whispers** — private, only sender (with `>>`) and target see it; other agents in the room do not
- **Yells** — broadcast via BFS up to 3 rooms: same room sees `Kael yells: "Help!"`, adjacent (1 hop) sees `Kael yells from the south (Great Hall): "Help!"`, 2-3 hops sees `Kael yells in the distance: "Help!"`
- **NPC dialogue** — long narrator-generated dialogue is LLM-summarized to 1-2 sentences before entering `lore_history` (full text still shown in event log)
- **No cross-room information** — if an ally moves away, you don't see what they do next (except yells)

## Architecture: Action Validation & Retry

When an agent produces an invalid action (e.g., fireballing an empty room, attacking an NPC):
1. The action is validated against the current game state
2. A dynamic list of valid actions is generated (only showing what's actually possible)
3. The model is re-prompted: "Your action was invalid. Evaluate each option, then choose."
4. Up to 2 retries; forces deliberation over real options instead of pattern-matching

## Architecture: Streaming Protocol

`POST /api/simulate?world_id=shadowfell` returns newline-delimited JSON:

```
{"type": "init", "world": {...}, "agents": [...]}
{"type": "event", "tick": 1, "event": {...}, "agent_states": [...], "room_states": {...}}
{"type": "event", "tick": 1, "event": {...}, "agent_states": [...], "room_states": {...}}
{"type": "tick", "tick": 1, "events": [...], "agent_states": [...], "room_states": {...}}
...
{"type": "done", "outcome": "victory", "total_ticks": 15}
```

- `event` messages stream live as each agent acts — frontend updates immediately
- `event` messages include `agent_states` and `room_states` so the UI updates agent panels and dungeon map in real-time
- `tick` messages are end-of-tick snapshots (belt-and-suspenders state sync)
- Frontend accumulates all events into a flat `allEvents` array — no tick-based grouping in the UI

## Frontend State Model

The UI is a continuous live event stream (no tick slider/playback controls):

- `allEvents: GameEventData[]` — every event across the entire simulation
- `latestAgentStates: AgentSnapshot[]` — updated on each event message
- `latestRoomStates: Record<string, RoomSnapshot>` — updated on each event message
- `simulation: SimulationResult` — outcome, world definition, agent info

`SimulationResult` does NOT contain ticks or per-tick event arrays. The `TickData` type was removed.

## Key Game Mechanics

- **Combat:** `weapon.atk - target.pdef` (min 1). Mobs counterattack after taking damage.
- **Magic:** `ring.mdmg * multiplier - target.mdef`. Spells cost MP (missile:1, fireball:3, poison:2, heal:2).
- **Healing:** Restores 30% max HP.
- **Poison:** 1 damage/tick for 3 ticks.
- **Item equip:** Auto-equip if better stats (ATK for weapon, PDEF for armor, MDMG for ring).
- **Sensory context:** Agents see current room contents (with item stats for comparison) + exit names + list of rooms they've visited (no adjacent room details to avoid cross-room targeting).
- **Communication:** 4 commands with different scopes — `tell` (room, targeted), `say` (room, broadcast), `whisper` (private, only sender+target see it), `yell` (multi-room, BFS up to 3 hops with distance-dependent text).
- **Target rules:** Enemies → attack/missile/fireball/poison. Allies → heal/tell/whisper. NPCs → tell only. Items → get only.
- **Rich failure messages:** Combat/heal failures explain what the target actually is (NPC, ally, dead mob, item) and list valid targets.

## Agent Prompt Design

**North star: Agents should reason, not follow rules.** The whole point of using LLMs is emergent behavior — if we're writing conditional warnings and behavioral nudges into prompts, we're just building a scripted game with extra steps. Give the model the game state and let it figure out what to do. The dynamic commands list prevents impossible actions; everything else is the model's job.

- **Action prompt essentials:** Identity + personality, quest, equipment/stats, three-category history (recent events + ally comms + NPC lore), sensory context (with item stats and visited rooms), dynamic commands, Think/Do format. No behavioral nudges or conditional warnings — the model reasons from the game state.
- **Comm prompt essentials:** Identity + personality, stats, sensory context, three-category history, available comm commands, Think/Comm format. Agents decide what's worth communicating on their own.
- **Information-first design:** Instead of rules ("don't heal at full HP"), give the model information it can reason from: item stats so it can compare gear, visited rooms so it can avoid backtracking, separated history categories so tactical info is never crowded out by dialogue.
- **Dynamic quest text:** `config.QUEST_DESCRIPTION` is set at runtime from each world's `meta.description`, so agents get world-specific objectives.
- **Dynamic commands:** `_build_commands_help()` in `agent.py` generates the action command list based on current state — only shows movement for exits that exist, combat spells the agent can afford, items if any on ground, NPC tell if NPCs have dialogue left. This prevents impossible actions without telling the model what to think.
- **Multi-line Think parsing:** `_parse_think_do()` and `_parse_think_comm()` capture everything between `Think:` and `Do:`/`Comm:` as reasoning, even across multiple lines.
- **NPC dialogue summarization:** Full narrator-generated NPC dialogue is shown in the event log, but an LLM-summarized 1-2 sentence version goes into agent `lore_history` (separate from tactical events and ally comms).
- **BASE_PERSONALITY** (in `config.py`): Shared personality emphasizing exploration, combat for loot, NPC interaction, and ally coordination — deliberately generic to work across any dungeon layout.
- **Free communication phase:** Each tick starts with a communication phase where agents can say/tell/whisper/yell without consuming their action. Only ally communication is allowed (no NPC tells). Agents can choose "none" to stay silent.

## Agent Color Scheme

- Kael (Warrior): red (`#ef4444`)
- Lyria (Mage): blue (`#3b82f6`)
- Finn (Ranger): green (`#22c55e`)

Defined in `types.ts` as `AGENT_COLORS` and used throughout DungeonMap, AgentPanel, EventLog.

## Common Tasks

- **Add a new agent:** Add template in `config.py` AGENT_TEMPLATES, add color in `types.ts` AGENT_COLORS
- **Add a spell:** Add to `combat.py` (resolve function), `config.py` (SPELL_COSTS), `agent.py` (command help text)
- **Add a new world:** Create `data/worlds/yourworld.json` with `meta` + `rooms` (see existing files for format). It auto-appears in the UI.
- **Add rooms to a world:** Edit the world's JSON in `data/worlds/`
- **Change LLM model:** Edit `llm.py` model parameter or config.py defaults
- **Frontend component:** All in `web/frontend/src/components/`, styled with Tailwind utility classes

## Working on This Project

- **Always update this file (CLAUDE.md)** when making changes that affect architecture, game mechanics, prompt structure, file responsibilities, or anything documented here. This is the source of truth for how the project works.
- **Always update README.md** when making changes that affect user-facing behavior: game mechanics, how to run, features, project structure, configuration, or anything a new reader would need to know.

## Things That No Longer Exist

- `TickControls.tsx` — deleted (no tick slider/playback)
- `TickData` interface — removed from `types.ts`
- `ticks` array on `SimulationResult` — removed
- Per-tick state in App.tsx (`currentTick`, `playing`, `liveFollow`, `speed`, `liveTick`) — all removed
- `memory.py` — disabled (to be rethought)
- Post-action comments — removed (was causing bad advice cascades between agents, and costing an extra LLM call per agent per tick)
- Global `last_tick_recap` / `actions_so_far` — replaced by room-scoped three-category witnessed events (action/comm/lore)
- Single flat `action_history` — split into three categories: `action_history`, `comm_history`, `lore_history`
- Round 0 planning discussion — replaced by per-tick communication phase (agents coordinate every tick, not just once)
- `build_discussion_prompt` / `get_agent_discussion` — removed with round 0
- Static `COMMANDS_HELP` — replaced by `_build_commands_help()` which generates dynamic commands based on current game state
