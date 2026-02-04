# NachoMUD

An AI-powered text-based dungeon crawler where Claude-controlled agents cooperate to descend through the Durnhollow fortress, battle monsters, and close the Shadowfell Rift.

## Overview

NachoMUD is a collaborative AI dungeon simulation that showcases multi-agent reasoning and strategic cooperation. Three AI-controlled adventurers—each with distinct personalities and combat roles—must work together to survive encounters with progressively dangerous monsters and ultimately defeat the final boss.

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
└── data/
    ├── world.json    # Dungeon layout and encounters
    └── memories/     # Per-agent memory storage
        ├── finn.json
        ├── kael.json
        └── lyria.json
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

[Add your license here]

## Notes

This project demonstrates:
- Multi-agent AI coordination
- Complex prompt engineering for behavioral control
- Real-time decision-making in a dynamic environment
- Integration of AI-generated narrative with game logic
