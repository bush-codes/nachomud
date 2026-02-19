# NachoMUD - Claude Code Context

## What is this?

AI-powered text-based dungeon crawler where 3 LLM-controlled agents (Kael the Warrior, Lyria the Mage, Finn the Ranger) cooperate to descend through a 15-room dungeon, battle monsters, and defeat a final boss. Successor to KinchoMUD (2007-2009) which used neuroevolution; this version uses modern LLMs.

## Project Structure

```
nachomud/
├── main.py              # CLI game loop (10 ticks default)
├── agent.py             # LLM prompting: round-0 planning, action phase, retry validation
├── combat.py            # Damage resolution: attack, missile, fireball, poison, heal
├── world.py             # Room loading, sensory context building (current + adjacent rooms)
├── models.py            # Dataclasses: Item, Mob, NPC, Room, AgentState, GameEvent
├── config.py            # Agent templates (3 agents), spell costs, LLM_BACKEND, MAX_TICKS
├── memory.py            # (unused — memory system disabled, to be rethought)
├── llm.py               # LLM abstraction (Anthropic SDK or Ollama)
├── narrator.py          # Story narration via LLM (room descriptions, combat flavor)
├── data/
│   ├── world.json       # 15-room dungeon definition (mobs, NPCs, items, exits)
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
│               ├── GameHeader.tsx   # Status badge, Run/Reset buttons
│               ├── DungeonMap.tsx   # SVG map with agent dots, room states
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

## Architecture: Game Loop

**Round 0 (one-time, before tick 1):**
- All agents are in room_1; each speaks a planning utterance (1 LLM call each)
- The plan is seeded into each agent's `action_history` as initial witnessed events

**Each tick (up to MAX_TICKS=10):**
1. **Action phase** — for each agent:
   a. Build sensory context (current room state) + witnessed events history
   b. Get action from LLM using Think/Do chain-of-thought format
   c. Validate action — if invalid, retry up to 2 times with a dynamic valid-actions list that forces the model to evaluate each option
   d. Resolve action → witnessed by all agents in the same room (room-scoped, not global)
   e. Movement: departure room sees "X leaves heading north", arrival room sees "X arrives from the south"
2. **Poison tick** — apply poison damage to affected mobs
3. **Win/loss check** — boss dead = victory, all agents dead = defeat

## Architecture: Witnessed Events (MUD Scrollback)

Agents only know what they've personally witnessed — like a real MUD player's scrollback:
- **Your own actions** prefixed with `>>` (e.g., `>> attack Goblin Guard → Kael attacks Goblin Guard for 5 damage.`)
- **Others' actions in your room** (e.g., `Lyria casts fireball! Goblin Scout SLAIN!`)
- **Arrivals/departures** (e.g., `Finn leaves heading north`, `Kael arrives from the south`)
- **No cross-room information** — if an ally moves away, you don't see what they do next

The `action_history` is a rolling window (capped at `ACTION_HISTORY_SIZE`, default 15) that replaces the old global `last_tick_recap` and `actions_so_far` systems.

## Architecture: Action Validation & Retry

When an agent produces an invalid action (e.g., fireballing an empty room, attacking an NPC):
1. The action is validated against the current game state
2. A dynamic list of valid actions is generated (only showing what's actually possible)
3. The model is re-prompted: "Your action was invalid. Evaluate each option, then choose."
4. Up to 2 retries; forces deliberation over real options instead of pattern-matching

## Architecture: Streaming Protocol

`POST /api/simulate` returns newline-delimited JSON:

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
- **Sensory context:** Agents see current room contents + exit names (no adjacent room details to avoid cross-room targeting).
- **Target rules:** Enemies → attack/missile/fireball/poison. Allies → heal/tell. NPCs → tell only. Items → get only.
- **Rich failure messages:** Combat/heal failures explain what the target actually is (NPC, ally, dead mob, item) and list valid targets.

## Agent Color Scheme

- Kael (Warrior): red (`#ef4444`)
- Lyria (Mage): blue (`#3b82f6`)
- Finn (Ranger): green (`#22c55e`)

Defined in `types.ts` as `AGENT_COLORS` and used throughout DungeonMap, AgentPanel, EventLog.

## Common Tasks

- **Add a new agent:** Add template in `config.py` AGENT_TEMPLATES, add color in `types.ts` AGENT_COLORS
- **Add a spell:** Add to `combat.py` (resolve function), `config.py` (SPELL_COSTS), `agent.py` (command help text)
- **Add rooms:** Edit `data/world.json` or extend narrator.py generation
- **Change LLM model:** Edit `llm.py` model parameter or config.py defaults
- **Frontend component:** All in `web/frontend/src/components/`, styled with Tailwind utility classes

## Things That No Longer Exist

- `TickControls.tsx` — deleted (no tick slider/playback)
- `TickData` interface — removed from `types.ts`
- `ticks` array on `SimulationResult` — removed
- Per-tick state in App.tsx (`currentTick`, `playing`, `liveFollow`, `speed`, `liveTick`) — all removed
- `memory.py` — disabled (to be rethought)
- Post-action comments — removed (was causing bad advice cascades between agents, and costing an extra LLM call per agent per tick)
- Global `last_tick_recap` / `actions_so_far` — replaced by room-scoped witnessed events
