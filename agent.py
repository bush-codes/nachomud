from __future__ import annotations

import anthropic

from config import AGENT_MODEL, ANTHROPIC_API_KEY, SPELL_COSTS
from memory import format_memories_for_prompt
from models import AgentState

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

COMMANDS_HELP = """Commands:
  n / s / e / w       - Move in a direction
  look                - Observe surroundings
  attack <mob>        - Melee attack (weapon ATK)
  missile <mob>       - Magic missile (1 MP, ring MDMG)
  fireball            - AoE all mobs (3 MP, ring MDMG x2)
  poison <mob>        - Poison: 1 dmg/tick, 3 ticks (2 MP)
  heal                - Restore 30% max HP (2 MP)
  get <item>          - Pick up item (auto-equips if better)
  tell <name> <msg>   - Speak to a specific NPC or ally
  say <message>       - Speak to everyone in the room"""


def build_agent_prompt(agent: AgentState, room_state: str) -> str:
    memories = format_memories_for_prompt(agent.name)

    last_action_line = ""
    if agent.last_action:
        last_action_line = f"\nYour last action: {agent.last_action}"
        if agent.last_result:
            last_action_line += f"\nResult: {agent.last_result}"

    prompt = f"""You are {agent.name} the {agent.agent_class}.
{agent.personality}

Your quest: descend through Durnhollow fortress, fight through its monsters, and close the Shadowfell Rift by defeating the final boss. You will die if you don't cooperate with your allies.

HP: {agent.hp}/{agent.max_hp} | MP: {agent.mp}/{agent.max_mp}
Weapon: {agent.weapon.name} (ATK:{agent.weapon.atk}) | Armor: {agent.armor.name} (PDEF:{agent.armor.pdef}) | Ring: {agent.ring.name} (MDMG:{agent.ring.mdmg})
Spell costs: missile={SPELL_COSTS['missile']}MP, fireball={SPELL_COSTS['fireball']}MP, poison={SPELL_COSTS['poison']}MP, heal={SPELL_COSTS['heal']}MP
{last_action_line}

=== CURRENT LOCATION ===
{room_state}

=== YOUR MEMORIES ===
{memories}

{COMMANDS_HELP}

The "Enemies:" line lists what you can fight. The "Items on ground:" line lists what you can pick up.
What do you do? Respond with exactly one command."""

    return prompt


def get_agent_action(agent: AgentState, room_state: str) -> str:
    prompt = build_agent_prompt(agent, room_state)

    response = client.messages.create(
        model=AGENT_MODEL,
        max_tokens=50,
        system=f"You are {agent.name} the {agent.agent_class} in a dungeon crawler. Output a single game command, nothing else.",
        messages=[{"role": "user", "content": prompt}],
    )

    raw = response.content[0].text.strip()
    # Take only the first line in case the LLM adds explanation
    action = raw.split("\n")[0].strip()
    # Remove any leading slash or punctuation
    if action.startswith("/"):
        action = action[1:]
    return action


def parse_action(action: str) -> tuple[str, str]:
    """Returns (command, argument). Argument may be empty."""
    parts = action.strip().split(None, 1)
    if not parts:
        return ("look", "")
    cmd = parts[0].lower()
    arg = parts[1] if len(parts) > 1 else ""
    return (cmd, arg)
