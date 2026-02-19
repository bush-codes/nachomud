# NachoMUD

An AI-powered text-based dungeon crawler where Claude-controlled agents cooperate to descend through the Durnhollow fortress, battle monsters, and close the Shadowfell Rift.

## Background: From Neuroevolution to Large Language Models

NachoMUD is the modern successor to **KinchoMUD** (2007-2009), an undergraduate research project at the University of Texas at Austin that explored whether AI agents could learn combat tactics in a MUD (Multi-User Dungeon) through neuroevolution.

### The Original Research: KinchoMUD & rtNEAT

KinchoMUD was a C++ MUD SDK built as a research platform for applying **rtNEAT** (real-time NeuroEvolution of Augmenting Topologies) to game AI. The project, conducted under UT Austin's Neural Networks research program, asked a series of progressively harder questions about emergent agent behavior:

- **Can agents learn that attacking is better than idling?** Neural networks with HP and MP as inputs evolved to choose between actions like *hit*, *cure*, *fire*, *poison*, and *crit* -- each with different damage, MP costs, and tradeoffs.
- **Can agents learn resource management?** Mobs successfully evolved to avoid casting cure when MP was zero, and to heal only when HP was critically low to maximize total damage output before death.
- **Can emergent "classes" form?** By constraining stat configurations (high HP/no MP, low HP/high MP), distinct combat roles naturally arose through evolution -- physical fighters, mage-types, and hybrids.
- **Can agents cooperate in parties?** The research designed a "party brain" architecture where individual mob brains could consult a shared party brain for recommended actions, then decide whether to follow or ignore the advice. Sub-brains for battle, movement, and party coordination gave each mob a modular decision architecture.
- **Can agents learn to lead and teach?** A 2007 proposal explored whether rtNEAT agents could be assigned military-style ranks and learn to advise subordinates, extending human-to-agent training research into agent-to-agent knowledge transfer.

The experiments showed that neuroevolution could produce agents that maximized damage given arbitrary skill configurations, learned when to use poison vs. cure, and developed rudimentary tactical behavior. However, the approach hit fundamental limits: agents couldn't generalize to novel situations, had no concept of narrative or communication, and the fitness functions needed careful hand-tuning for each new behavior.

This research culminated in two undergraduate honors theses at UT Austin's AI Lab:
- [Christopher Bush, "KinchoMUD: Applying rtNEAT to a Multi-User Dungeon" (2010)](https://www.cs.utexas.edu/~ai-lab/?bush:ugthesis10)
- [Matthew Johnston, "KinchoMUD: Applying rtNEAT to a Multi-User Dungeon" (2010)](https://www.cs.utexas.edu/~ai-lab/?johnston:ugthesis10)

### The Legacy Codebase

The original project lives in the `neatMUD/` directory:

- **`neatMUD/kinchoMUD/`** -- The C++ MUD SDK with rooms, mobs, battles, stats, and a `MobBrain` class wired to rtNEAT neural network populations for real-time mob decision-making
- **`neatMUD/rtNEAT/`** -- Kenneth Stanley's rtNEAT library (C++) for evolving neural network topologies in real time
- **`neatMUD/kinchoMUD/docs/Research/`** -- Original research reports and proposals from 2007-2009

#### Building & Running KinchoMUD

The legacy C++ codebase compiles with a modern g++ toolchain. The rtNEAT library must be built first as a static archive, then linked into KinchoMUD.

**1. Build rtNEAT library:**

```bash
cd neatMUD/rtNEAT
make librtneat.a
```

**2. Build KinchoMUD with rtNEAT:**

```bash
cd ../kinchoMUD
g++ -O0 -g3 -std=c++14 -Wno-write-strings -Wno-address \
    -I../rtNEAT \
    -o kinchoMUD \
    src/spoc2.cpp src/Console.cpp src/Login.cpp src/Mob.cpp \
    src/MobBrain.cpp src/Player.cpp src/Room.cpp src/Stat.cpp \
    ../rtNEAT/librtneat.a
```

**3. Run:**

```bash
./kinchoMUD
```

Log in as `kincho` at the prompt. You'll spawn in the Center Hallway with a penguin. Try commands like `look`, `north`, `hit goblin`, `cure`, `fire`, and `poison`.

#### Battle Simulations

KinchoMUD includes two automated battle simulation modes used in the original research:

- **`auto 0 goblin`** -- 1v1 autoBattle. The player auto-attacks while the goblin uses its evolved neural network brain to choose actions. Runs in an infinite loop, printing fitness and action counts per encounter.
- **`auto 1 goblin`** -- Multi-agent party combat (autoBattle2). A 3v1 party of Paladin, Magician, and Sorcerer vs. a Skeleton across 250,000 encounters. Each mob's brain evolves independently via rtNEAT, with per-encounter stats showing action counts and fitness scores.

These simulations demonstrate how rtNEAT evolves combat tactics: agents learn to prefer attacking over idling, manage MP for spells like cure and poison, and develop distinct behavioral profiles based on their stat configurations.

### NachoMUD: The Next Iteration

NachoMUD revisits the same core questions -- *can AI agents make strategic combat decisions, cooperate in parties, and behave with distinct personalities?* -- but replaces neuroevolution with large language models.

Where KinchoMUD needed thousands of generations to evolve a neural network that could learn "heal when HP is low," NachoMUD's Claude-powered agents understand that concept from their first turn. The shift from rtNEAT to LLMs transforms what's possible:

| | KinchoMUD (2007-2009) | NachoMUD (2025) |
|---|---|---|
| **AI Architecture** | rtNEAT neural networks | Claude (LLM) |
| **Decision Making** | Evolved fitness functions | Natural language reasoning |
| **Learning** | Generational evolution over thousands of episodes | In-context via persistent memory |
| **Communication** | None (isolated brains) | Natural language dialogue between agents |
| **Personality** | Emergent from network weights | Defined character traits influencing decisions |
| **Narration** | Static text strings | Dynamic AI-generated storytelling |
| **Party Coordination** | Proposed "party brain" architecture | Agents speak, strategize, and coordinate naturally |
| **Language** | C++ | Python |

The original research dreamed of agents that could talk to each other, form strategies, and develop distinct roles. Fifteen years and a paradigm shift in AI later, NachoMUD makes that a reality.

## Overview

NachoMUD is a collaborative AI dungeon simulation that showcases multi-agent reasoning and strategic cooperation. Three AI-controlled adventurers -- each with distinct personalities and combat roles -- must work together to survive encounters with progressively dangerous monsters and ultimately defeat the final boss.

The game uses **Claude** or local LLMs via **Ollama** to power real-time decision-making for all agents, including combat actions and tactical coordination. The narrator also uses LLMs to generate dynamic, story-driven descriptions of events.

## Features

- **AI-Driven Agents**: Three autonomous characters (Kael the Warrior, Lyria the Mage, Finn the Ranger) make strategic decisions using Claude or local LLMs via Ollama
- **Round-0 Planning + Action Phases**: Agents discuss strategy once before tick 1, then each tick they act based on what they've personally witnessed (room-scoped, like a MUD scrollback)
- **Witnessed Events Model**: Agents only know what they've seen in their room -- no global information leaking. Own actions prefixed with `>>`, others' actions observed naturally, arrivals/departures tracked
- **Action Validation & Retry**: Invalid actions are caught and the model is re-prompted with a dynamic valid-actions list, forcing deliberation over real options
- **Sensory Awareness**: Agents see their current room contents and exit names, eliminating the need for explicit "look" commands
- **Real-Time Combat System**: Attack, magic spells (missile, fireball, poison), healing, and item management with rich failure messages
- **Procedural Narration**: LLM-generated story narration for combat and dialogue
- **Dynamic World**: 15-room fortress with NPCs, loot, and escalating mob difficulty
- **Cooperative Gameplay**: Agents coordinate through witnessed actions and room-scoped awareness
- **Web Visualization**: Real-time streaming UI with live events, dungeon map, agent panels, and simulation controls

## Project Structure

```
nachomud/
├── main.py              # CLI game loop (10 ticks default)
├── agent.py             # LLM prompting: round-0 planning, action phase, retry validation
├── llm.py               # LLM abstraction (Anthropic SDK or Ollama)
├── combat.py            # Damage resolution: attack, missile, fireball, poison, heal
├── world.py             # Room loading, sensory context building
├── narrator.py          # LLM-powered story narration (room descriptions, combat flavor)
├── models.py            # Dataclasses: Item, Mob, NPC, Room, AgentState, GameEvent
├── config.py            # Agent templates (3 agents), spell costs, LLM_BACKEND, MAX_TICKS
├── run.sh               # Launch script (Ollama + backend + frontend)
├── requirements.txt     # Python dependencies
├── data/
│   ├── world.json       # 15-room dungeon definition (mobs, NPCs, items, exits)
│   └── logs/            # Simulation transcripts (auto-generated)
├── web/                     # Web visualization
│   ├── backend/
│   │   └── server.py        # FastAPI server - streams simulation as NDJSON
│   └── frontend/            # React 19 + TypeScript + Vite 6 + Tailwind CSS
│       └── src/
│           ├── App.tsx           # Main component: streaming state management
│           ├── types.ts          # TS interfaces matching backend models
│           └── components/
│               ├── GameHeader.tsx   # Status badge, Run/Reset buttons
│               ├── DungeonMap.tsx   # SVG map with agent dots, room states
│               ├── AgentPanel.tsx   # HP/MP bars, equipment, last action
│               └── EventLog.tsx     # Color-coded live event stream
└── neatMUD/                 # Legacy research codebase (2007-2009)
    ├── kinchoMUD/           # Original C++ MUD SDK with rtNEAT integration
    │   ├── src/             # Battle, Mob, MobBrain, Chain, Room, etc.
    │   ├── data/            # XML world definitions
    │   └── docs/            # Research reports and proposals
    └── rtNEAT/              # Kenneth Stanley's rtNEAT neuroevolution library
```

## Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd nachomud
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Set up your LLM backend (choose one):

**Option A: Anthropic API (Claude)**
```bash
export ANTHROPIC_API_KEY="your-api-key-here"
```

**Option B: Local LLM with Ollama (free, no API key needed)**
```bash
# Install Ollama
curl -fsSL https://ollama.com/install.sh | sh

# Pull a model
ollama pull qwen2.5:7b

# Set the backend
export LLM_BACKEND=ollama
```

## Usage

### Quick Start with `run.sh`

The easiest way to run NachoMUD is with the launch script, which handles starting Ollama (if needed) and the web server:

```bash
./run.sh
```

By default `run.sh` uses the Ollama backend. To use Claude instead:

```bash
LLM_BACKEND=anthropic ./run.sh
```

### Running Manually

**CLI mode:**
```bash
python main.py
```

The simulation will run for up to 10 ticks (turns), with each agent deciding their action based on what they've witnessed. Watch as the AI-controlled party descends through the fortress!

### Local LLM (Ollama)

NachoMUD can run entirely locally using [Ollama](https://ollama.com) instead of the Anthropic API. This is free, requires no API key, and keeps all inference on your machine.

**Setup:**
```bash
# Install Ollama (Linux/macOS)
curl -fsSL https://ollama.com/install.sh | sh

# Pull the default model (~4GB)
ollama pull qwen2.5:7b

# Run with Ollama
LLM_BACKEND=ollama python main.py
```

**Recommended models:**

| Model | Size | Notes |
|---|---|---|
| `qwen2.5:7b` (default) | ~4GB VRAM | Good instruction following, handles structured output well |
| `llama3.2:3b` | ~2GB VRAM | Lighter alternative for low-resource machines |

**Environment variables:**

| Variable | Default | Description |
|---|---|---|
| `LLM_BACKEND` | `ollama` | LLM backend: `anthropic` or `ollama` |
| `AGENT_MODEL` | Backend-dependent | Model for agent decisions |
| `NARRATOR_MODEL` | Backend-dependent | Model for narration and world generation |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama server URL (for remote Ollama instances) |
| `ANTHROPIC_API_KEY` | *(empty)* | Anthropic API key (required for `anthropic` backend) |

### Web Visualization

NachoMUD includes a web-based simulation viewer that lets you run simulations and replay them tick-by-tick with an interactive dungeon map, agent stat panels, and a color-coded event log.

**1. Install backend dependencies:**

```bash
pip install fastapi uvicorn
```

**2. Build the frontend:**

```bash
cd web/frontend
npm install
npm run build
```

**3. Start the server:**

```bash
# With Ollama (no API key needed):
LLM_BACKEND=ollama cd web/backend && uvicorn server:app --port 4000

# Or with Claude:
export ANTHROPIC_API_KEY="your-api-key-here"
cd web/backend && uvicorn server:app --port 4000

# Or just use run.sh:
./run.sh
```

Open `http://localhost:4000` and click **Run Simulation**.

For frontend development with hot reload, run the Vite dev server in a separate terminal:

```bash
# Terminal 1
cd web/backend && uvicorn server:app --port 4000

# Terminal 2
cd web/frontend && npm run dev
```

The Vite dev server proxies API requests to the backend automatically.

## Game Mechanics

### Characters

- **Kael** (Warrior): High HP, melee-focused, protective of allies
- **Lyria** (Mage): Lower HP, magic-focused, support capabilities
- **Finn** (Ranger): Balanced stats, scouts ahead, practical and observant

### Combat Actions

- `attack <mob>` - Melee attack using weapon ATK
- `missile <mob>` - Single-target magic missile (1 MP, uses ring MDMG)
- `fireball` - Area-of-effect spell hitting all mobs (3 MP, ring MDMG x2)
- `poison <mob>` - Apply poison (2 MP, 1 damage/tick for 3 ticks)
- `heal` - Restore 30% max HP (2 MP)

### Movement & Interaction

- `n / s / e / w` - Move in cardinal directions
- `get <item>` - Pick up loot (auto-equips if better)
- `tell <name> <msg>` - Speak to an NPC or ally
- `say <message>` - Speak to everyone in the room

Agents see their current room contents and exit names, so there is no `look` command -- they always know what's in their room.

### Equipment

Items have four stats:
- **ATK**: Physical attack damage (weapons)
- **PDEF**: Physical defense (armor/rings)
- **MDEF**: Magic defense (armor/rings)
- **MDMG**: Magic damage (rings)

## Configuration

Edit `config.py` to customize:

- `AGENT_TEMPLATES`: Character stats, personality, starting equipment
- `MAX_TICKS`: Maximum game length
- `SPELL_COSTS`: Magic point costs for spells
- `HEAL_PERCENT`: Healing spell effectiveness
- `POISON_DURATION` / `POISON_DAMAGE`: Status effect parameters
- `NARRATOR_MODEL` / `AGENT_MODEL`: Claude model versions to use

## World Data

The dungeon layout, encounters, and items are defined in `data/world.json`. Each room can contain:
- NPCs with dialogue
- Mobs with varying difficulty
- Loot items
- Connections to adjacent rooms

Simulation logs are written to `data/logs/` for each run.

## Technology

- **Claude AI or Ollama**: Powers all agent decisions and narration (configurable via `LLM_BACKEND`)
- **Python 3.10+**: Core language
- **Anthropic SDK**: Integration with Claude API
- **Ollama**: Local LLM inference (optional)
- **FastAPI + Uvicorn**: Web visualization backend
- **React + TypeScript + Tailwind CSS**: Web visualization frontend (Vite build)

## Requirements

- Python 3.10 or higher
- `anthropic>=0.40.0`
- `ollama>=0.4.0` (for local LLM backend)
- `fastapi>=0.110.0`, `uvicorn>=0.27.0` (for web visualization)
- Node.js 18+ and npm (for building the frontend)
- Valid Anthropic API key **or** Ollama installed locally

## License

MIT License -- see [LICENSE](LICENSE) for details.

The `neatMUD/rtNEAT/` directory contains Kenneth Stanley's rtNEAT library, which is Copyright (c) The University of Texas at Austin, 2006, and is released under a separate UT Austin Research License for non-commercial/research use only. It is not covered by the MIT license.
