# NachoMUD

An AI-powered text-based dungeon crawler where LLM-controlled agents cooperate to navigate dungeons, battle monsters, and defeat final bosses. Select a party of 3 from 6 unique character classes, each with their own abilities and playstyle. Features speed-based initiative, LLM-driven mob turns, a buff/debuff system, and multiple worlds with different topologies to test agent generalization.

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

NachoMUD is a collaborative AI dungeon simulation that showcases multi-agent reasoning and strategic cooperation. Select a party of 3 from 6 character classes -- each with unique abilities and combat roles -- and watch as they work together to survive encounters with progressively dangerous monsters and defeat the final boss.

The game uses **Claude** or local LLMs via **Ollama** to power real-time decision-making for all agents and monsters, including combat actions, tactical coordination, and in-character dialogue. The narrator also uses LLMs to generate dynamic story-driven descriptions.

## Features

- **6 Character Classes**: Warrior, Paladin, Mage, Cleric, Ranger, Rogue -- each with 5 unique abilities and distinct stats
- **Party Selection**: Choose 3 classes for your party composition (default: Warrior, Mage, Ranger)
- **24 Unique Abilities**: Physical attacks, magic, healing, buffs, debuffs, crowd control -- zero overlap between classes
- **Speed-Based Initiative**: Agents and mobs act in speed order (Rogue at 6, Mage at 4, Warrior at 3)
- **LLM-Driven Mob Turns**: Monsters make their own decisions using LLM reasoning, with taunt/sleep enforcement
- **Buff/Debuff System**: Defend, ward, barrier, evade, rally, shield, taunt, sleep, curse, poison, bleed, smoke bomb
- **Communication + Action Phases**: Each tick has a free communication phase (say/tell/whisper/yell) followed by interleaved agent and mob action turns
- **Witnessed Events Model**: Agents only know what they've seen in their room -- no global information leaking
- **Dynamic Commands & Retry**: Action prompts only show class-appropriate commands relevant to current state. Invalid actions trigger retry
- **Deterministic Combat**: All damage formulas are deterministic (no RNG/hit chance)
- **Class-Specific Equipment**: Items can be restricted to certain classes. Agents see `[CANNOT USE]` on wrong-class gear
- **Multiple Worlds**: 4 hand-crafted dungeons with different topologies (linear, hub-and-spoke, ring/loop, wide branching)
- **Web Visualization**: Real-time streaming UI with party selector, dungeon map, agent panels with status effects, and event log
- **Comprehensive Tests**: 224 tests covering abilities, effects, initiative, mob AI, equipment, engine, and world data

## Project Structure

```
nachomud/
├── main.py              # CLI game loop (20 ticks default)
├── engine.py            # Core game logic: agents, actions, initiative, witnesses
├── abilities.py         # 24 ability resolvers (registry pattern)
├── effects.py           # StatusEffect system: buffs, debuffs, DoTs
├── mob_ai.py            # LLM-driven mob turns
├── agent.py             # LLM prompting: comm/action phases, class-specific commands
├── combat.py            # Legacy damage resolution
├── world.py             # Room loading, world listing, sensory context
├── narrator.py          # LLM-powered story narration
├── models.py            # Dataclasses: Item, Mob, NPC, Room, AgentState, StatusEffect
├── config.py            # CLASS_DEFINITIONS, ABILITY_DEFINITIONS, LLM settings
├── llm.py               # LLM abstraction (Anthropic SDK or Ollama)
├── run.sh               # Launch script (Ollama + backend + frontend)
├── tests/               # 224 pytest tests
├── data/
│   ├── worlds/          # World JSON files (one per dungeon)
│   │   ├── shadowfell.json    # 15-room linear fortress
│   │   ├── frostpeak.json     # 13-room hub-and-spoke frozen citadel
│   │   ├── serpentmire.json   # 12-room ring/loop swamp
│   │   └── emberhollows.json  # 14-room wide branching volcanic caverns
│   └── logs/            # Simulation transcripts (auto-generated)
├── web/
│   ├── backend/
│   │   └── server.py        # FastAPI server - streams simulation as NDJSON
│   └── frontend/            # React 19 + TypeScript + Vite 6 + Tailwind CSS
│       └── src/
│           ├── App.tsx           # Streaming state management, party selection
│           ├── types.ts          # TS interfaces, class colors
│           └── components/
│               ├── GameHeader.tsx    # Status, world/model selectors, controls
│               ├── DungeonMap.tsx    # SVG map with auto-layout
│               ├── AgentPanel.tsx    # HP/MP/AP bars, status effects, equipment
│               ├── EventLog.tsx      # Color-coded event stream
│               └── PartySelector.tsx # 6-class party picker
└── neatMUD/                 # Legacy research codebase (2007-2009)
    ├── kinchoMUD/           # Original C++ MUD SDK with rtNEAT integration
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
ollama pull gemma3:4b

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

The simulation will run for up to 20 ticks (turns). Each tick, agents first communicate (warnings, coordination, intel), then agents and mobs act in speed order based on what they've witnessed. Watch as the AI-controlled party explores the dungeon!

### Web Visualization

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

Open `http://localhost:4000`, select your party of 3, and click **Run Simulation**.

For frontend development with hot reload, run the Vite dev server in a separate terminal:

```bash
# Terminal 1
cd web/backend && uvicorn server:app --port 4000

# Terminal 2
cd web/frontend && npm run dev
```

### Running Tests

```bash
pytest tests/          # All 224 tests
pytest tests/ -x       # Stop at first failure
pytest tests/ -v       # Verbose output
```

### Local LLM (Ollama)

NachoMUD can run entirely locally using [Ollama](https://ollama.com) instead of the Anthropic API. This is free, requires no API key, and keeps all inference on your machine.

**Setup:**
```bash
# Install Ollama (Linux/macOS)
curl -fsSL https://ollama.com/install.sh | sh

# Pull the default model (~2GB)
ollama pull gemma3:4b

# Run with Ollama
LLM_BACKEND=ollama python main.py
```

**Recommended models:**

| Model | Size | Notes |
|---|---|---|
| `gemma3:4b` (default) | ~2GB VRAM | Fast, good instruction following |
| `gemma3:12b` | ~8GB VRAM | Better reasoning, recommended for challenging worlds |
| `qwen2.5:7b` | ~4GB VRAM | Good structured output, handles complex prompts well |

**Environment variables:**

| Variable | Default | Description |
|---|---|---|
| `LLM_BACKEND` | `ollama` | LLM backend: `anthropic` or `ollama` |
| `AGENT_MODEL` | Backend-dependent | Model for agent and mob decisions |
| `NARRATOR_MODEL` | Backend-dependent | Model for narration and world generation |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama server URL |
| `ANTHROPIC_API_KEY` | *(empty)* | Anthropic API key (required for `anthropic` backend) |

## Game Mechanics

### Character Classes

| Class | HP | Resource | Speed | Role |
|-------|-----|----------|-------|------|
| **Warrior** | 25 | AP:10 | 3 | Tank/DPS. Cleave for AoE, taunt to protect allies, defend/rally for buffs |
| **Paladin** | 20 | MP:8 | 3 | Tank/healer. Smite for holy damage, lay on hands for strong heals, shield to protect allies |
| **Mage** | 8 | MP:25 | 4 | Glass cannon. Missile/arcane storm for magic damage, curse for DoT, barrier for defense |
| **Cleric** | 14 | MP:18 | 3 | Primary healer. Heal/ward for sustain, holy bolt for damage, cure to remove debuffs |
| **Ranger** | 14 | MP:10 | 5 | Ranged DPS/CC. Aimed shot for single-target, volley for AoE, poison/sleep for control |
| **Rogue** | 12 | MP:8 | 6 | Fastest class. Backstab for burst damage (costs HP), bleed for DoT, evade/smoke bomb for survival |

### Abilities

**Damage:**
- `attack` - Basic melee (weapon ATK vs PDEF, free)
- `cleave` - AoE melee all mobs (3 AP, Warrior)
- `smite` - Holy strike: ATK*1.5 vs MDEF (2 MP, Paladin)
- `consecrate` - Holy AoE: ATK vs MDEF per mob (4 MP, Paladin)
- `missile` - Magic missile: MDMG vs MDEF (1 MP, Mage)
- `arcane_storm` - AoE: MDMG*2 vs MDEF per mob (4 MP, Mage)
- `holy_bolt` - Holy bolt: MDMG*1.5 vs MDEF (2 MP, Cleric)
- `aimed_shot` - ATK*2 vs PDEF (3 MP, Ranger)
- `volley` - AoE: ATK vs PDEF per mob (3 MP, Ranger)
- `backstab` - ATK*2.5, ignores defense (3 HP, Rogue)

**Healing & Support:**
- `heal` - Restore 30% max HP (2 MP, Cleric)
- `lay_on_hands` - Restore 40% max HP (3 MP, Paladin)
- `cure` - Remove all debuffs (1 MP, Cleric)

**Buffs:**
- `defend` - Reduce incoming damage by 50% for 1 tick (2 AP, Warrior)
- `rally` - All allies deal +2 damage on next hit (4 AP, Warrior)
- `ward` - Reduce damage by 3 for 3 ticks (2 MP, Cleric)
- `barrier` - Absorb 8 damage (3 MP, Mage)
- `evade` - Next attack deals 0 damage (2 HP, Rogue)
- `shield` - Redirect next attack on ally to Paladin (2 MP, Paladin)

**Debuffs & CC:**
- `curse` - 2 dmg/tick for 3 ticks (2 MP, Mage)
- `poison_arrow` - 2 dmg/tick for 3 ticks (2 MP, Ranger)
- `bleed` - 2 dmg/tick for 3 ticks (2 MP, Rogue)
- `taunt` - Force all mobs to target Warrior (2 AP, Warrior)
- `sleep` - Target skips next 2 turns (3 MP, Ranger)
- `smoke_bomb` - All mobs deal -3 damage for 2 ticks (3 MP, Rogue)

### Movement & Interaction

- `n / s / e / w` - Move in cardinal directions
- `get <item>` - Pick up loot (auto-equips if better, respects class restrictions)

### Communication

Each tick begins with a **free communication phase** where agents can talk without consuming their action:

- `tell <name> <msg>` - Speak to an NPC or ally (everyone in room hears)
- `say <message>` - Speak to everyone in the room
- `whisper <ally> <msg>` - Private message to an ally (only they hear)
- `yell <message>` - Shout heard up to 3 rooms away (distance-dependent text)
- `none` - Stay silent

### Initiative System

Each tick, all living entities (agents + mobs) act in speed order:
1. Higher speed goes first (Rogue: 6, Ranger: 5, Mage: 4, others: 3)
2. On ties: agents before mobs, then alphabetical

Warriors regenerate 3 AP per tick (capped at max). All other resource costs are paid from MP or HP.

### Monster AI

Mobs have their own LLM-driven turns:
- Each mob has defined abilities (e.g., Goblin Shaman: attack, curse, heal)
- Bosses always communicate before acting (taunts, threats)
- Taunt enforcement: taunted mobs must attack the taunter
- Sleep enforcement: sleeping mobs skip their turn entirely

### Equipment

Items have four stats: **ATK** (physical damage), **PDEF** (physical defense), **MDEF** (magic defense), **MDMG** (magic damage).

Items can be restricted to certain classes via `allowed_classes`. Agents see `[CANNOT USE]` when viewing restricted items they can't equip.

## Configuration

Edit `config.py` to customize:

- `CLASS_DEFINITIONS`: 6 character classes with stats, abilities, default names, equipment
- `ABILITY_DEFINITIONS`: 24 abilities with costs, target types, descriptions
- `MAX_TICKS`: Maximum game length (default: 20)
- `AGENT_MODEL` / `NARRATOR_MODEL`: LLM model selection

## Worlds

NachoMUD ships with 4 hand-crafted worlds, each with a distinct topology designed to test different aspects of agent cooperation:

| World | Rooms | Topology | Boss |
|---|---|---|---|
| **Shadowfell Rift** | 15 | Linear with side branches | Void Lord Malachar |
| **Frostpeak Citadel** | 13 | Hub-and-spoke (3 wings from central hall) | Frost Titan Valdris |
| **The Serpent's Mire** | 12 | Ring/loop (multiple routes to boss) | Naga Sorceress Ssythara |
| **The Ember Hollows** | 14 | Wide branching tree (split/reconverge) | Magma Drake Pyraxis |

World files live in `data/worlds/` as JSON. Each file contains a `meta` block (name, description) and a `rooms` array with mobs that have abilities, speed, personality, and defense stats. To add a new world, create a JSON file in `data/worlds/` -- it will automatically appear in the UI's world selector dropdown.

## Technology

- **Claude AI or Ollama**: Powers all agent and mob decisions plus narration (configurable via `LLM_BACKEND`)
- **Python 3.10+**: Core language
- **Anthropic SDK**: Integration with Claude API
- **Ollama**: Local LLM inference (optional)
- **FastAPI + Uvicorn**: Web visualization backend
- **React + TypeScript + Tailwind CSS**: Web visualization frontend (Vite build)
- **pytest**: 224 tests covering all game systems

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
