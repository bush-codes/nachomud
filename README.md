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

The game uses **Claude Sonnet 4** to power real-time decision-making for all agents, including combat actions, dialogue, and tactical coordination. The narrator also uses Claude to generate dynamic, story-driven descriptions of events.

## Features

- **AI-Driven Agents**: Three autonomous characters (Kael the Warrior, Finn the Rogue, Lyria the Mage) make strategic decisions using Claude
- **Real-Time Combat System**: Attack, magic spells (missile, fireball, poison), healing, and item management
- **Procedural Narration**: Claude-generated story narration for combat and dialogue
- **Persistent Memory**: Agents maintain memories of past events that influence future decisions
- **Dynamic World**: Multi-room fortress with NPCs, loot, and escalating mob difficulty
- **Cooperative Gameplay**: Agents must coordinate to survive encounters

## Project Structure

```
nachomud/
├── main.py           # Game loop and orchestration
├── agent.py          # Agent decision-making and action parsing
├── combat.py         # Combat resolution system
├── world.py          # World and room management
├── memory.py         # Agent memory and narrative construction
├── narrator.py       # Claude-powered story narration
├── models.py         # Data structures (Agent, Room, Mob, etc.)
├── config.py         # Configuration and templates
├── requirements.txt  # Python dependencies
├── data/
│   ├── world.json    # Dungeon layout and encounters
│   └── memories/     # Per-agent memory storage
│       ├── finn.json
│       ├── kael.json
│       └── lyria.json
└── neatMUD/              # Legacy research codebase (2007-2009)
    ├── kinchoMUD/        # Original C++ MUD SDK with rtNEAT integration
    │   ├── src/          # Battle, Mob, MobBrain, Chain, Room, etc.
    │   ├── data/         # XML world definitions
    │   └── docs/         # Research reports and proposals
    └── rtNEAT/           # Kenneth Stanley's rtNEAT neuroevolution library
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

3. Set up your Anthropic API key:
```bash
export ANTHROPIC_API_KEY="your-api-key-here"
```

## Usage

Run the game:
```bash
python main.py
```

The simulation will run for up to 50 ticks (turns), with each agent deciding their action and the narrator describing the results. Watch as the AI-controlled party descends through the fortress!

## Game Mechanics

### Characters

- **Kael** (Warrior): High HP, melee-focused, protective of allies
- **Finn** (Rogue): Balanced stats, tactical approach, precise strikes
- **Lyria** (Mage): Lower HP, magic-focused, support capabilities

### Combat Actions

- `attack <mob>` - Melee attack using weapon ATK
- `missile <mob>` - Single-target magic missile (1 MP, uses ring MDMG)
- `fireball` - Area-of-effect spell hitting all mobs (3 MP, ring MDMG x2)
- `poison <mob>` - Apply poison (2 MP, 1 damage/tick for 3 ticks)
- `heal` - Restore 30% max HP (2 MP)

### Movement & Interaction

- `n / s / e / w` - Move in cardinal directions
- `look` - Examine current room
- `get <item>` - Pick up loot (auto-equips if better)
- `tell <name> <msg>` - Speak to an NPC or ally
- `say <message>` - Speak to everyone in the room

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

Agent memories are stored in `data/memories/` for persistence between decisions.

## Technology

- **Claude AI**: Powers all agent decisions and narration
- **Python 3.10+**: Core language
- **Anthropic SDK**: Integration with Claude API

## Requirements

- Python 3.10 or higher
- `anthropic>=0.40.0`
- Valid Anthropic API key

## License

MIT License -- see [LICENSE](LICENSE) for details.

The `neatMUD/rtNEAT/` directory contains Kenneth Stanley's rtNEAT library, which is Copyright (c) The University of Texas at Austin, 2006, and is released under a separate UT Austin Research License for non-commercial/research use only. It is not covered by the MIT license.
