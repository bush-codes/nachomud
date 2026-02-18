from __future__ import annotations

from config import AGENT_MODEL, SPELL_COSTS
from llm import chat
from memory import format_memories_for_prompt
from models import AgentState

COMMANDS_HELP = """Commands:
  n / s / e / w       - Move in a direction
  attack <mob>        - Melee attack (weapon ATK)
  missile <mob>       - Magic missile (1 MP, ring MDMG)
  fireball            - AoE all mobs (3 MP, ring MDMG x2)
  poison <mob>        - Poison: 1 dmg/tick, 3 ticks (2 MP)
  heal                - Restore 30% max HP (2 MP)
  get <item>          - Pick up item (auto-equips if better)
  tell <name> <msg>   - Speak to a specific NPC or ally
  say <message>       - Speak to everyone in the room"""


def build_discussion_prompt(agent: AgentState, sensory: str, allies: list[str], discussion_so_far: list[str]) -> str:
    memories = format_memories_for_prompt(agent.name)

    last_action_line = ""
    if agent.last_action:
        last_action_line = f"\nYour last action: {agent.last_action}"
        if agent.last_result:
            last_action_line += f"\nResult: {agent.last_result}"

    discussion_block = ""
    if discussion_so_far:
        discussion_block = "\n=== DISCUSSION THIS TURN ===\n" + "\n".join(discussion_so_far)

    prompt = f"""You are {agent.name} the {agent.agent_class}.
{agent.personality}

Your quest: descend through Durnhollow fortress, fight through its monsters, and close the Shadowfell Rift by defeating the final boss. You will die if you don't cooperate with your allies.

HP: {agent.hp}/{agent.max_hp} | MP: {agent.mp}/{agent.max_mp}
{last_action_line}

=== WHAT YOU SEE ===
{sensory}

=== YOUR MEMORIES ===
{memories}
{discussion_block}

{COMMANDS_HELP}

{"You are alone here. Think out loud about your situation and what you should do. Being separated from allies is dangerous." if not allies else "You are discussing strategy with your allies before acting."} Consider enemies to fight, items to pick up, NPCs to talk to, and exits to explore. Picking up items automatically equips them if they are better than your current gear. What should {"you" if not allies else "the group"} do next? Speak in character in 1-2 short sentences."""

    return prompt


def get_agent_discussion(agent: AgentState, sensory: str, allies: list[str], discussion_so_far: list[str]) -> str:
    prompt = build_discussion_prompt(agent, sensory, allies, discussion_so_far)

    raw = chat(
        system=f"You are {agent.name} the {agent.agent_class}. Speak in character in 1-2 sentences about what the group should do next. Consider everything you see: enemies to fight, items on the ground to pick up, NPCs to talk to, and exits to explore.",
        message=prompt,
        model=AGENT_MODEL,
        max_tokens=100,
    )
    utterance = raw.strip().split("\n")[0].strip()
    return utterance


def build_action_prompt(agent: AgentState, sensory: str, discussion: list[str], actions_so_far: list[str]) -> str:
    memories = format_memories_for_prompt(agent.name)

    last_action_line = ""
    if agent.last_action:
        last_action_line = f"\nYour last action: {agent.last_action}"
        if agent.last_result:
            last_action_line += f"\nResult: {agent.last_result}"

    discussion_block = ""
    if discussion:
        discussion_block = "\n=== DISCUSSION THIS TURN ===\n" + "\n".join(discussion)

    actions_block = ""
    if actions_so_far:
        actions_block = "\n=== ACTIONS SO FAR THIS TURN ===\n" + "\n".join(actions_so_far)

    prompt = f"""You are {agent.name} the {agent.agent_class}.
{agent.personality}

Your quest: descend through Durnhollow fortress, fight through its monsters, and close the Shadowfell Rift by defeating the final boss. You will die if you don't cooperate with your allies.

=== YOUR EQUIPMENT ===
Weapon: {agent.weapon.name} (ATK:{agent.weapon.atk}) | Armor: {agent.armor.name} (PDEF:{agent.armor.pdef}) | Ring: {agent.ring.name} (MDMG:{agent.ring.mdmg})
HP: {agent.hp}/{agent.max_hp} | MP: {agent.mp}/{agent.max_mp}
Spell costs: missile={SPELL_COSTS['missile']}MP, fireball={SPELL_COSTS['fireball']}MP, poison={SPELL_COSTS['poison']}MP, heal={SPELL_COSTS['heal']}MP
{last_action_line}

=== WHAT YOU SEE ===
{sensory}

=== YOUR MEMORIES ===
{memories}
{discussion_block}
{actions_block}

{COMMANDS_HELP}

Based on the discussion and what you see, what do you do? Respond with exactly one command."""

    return prompt


def get_agent_action(agent: AgentState, sensory: str, discussion: list[str], actions_so_far: list[str] | None = None) -> str:
    prompt = build_action_prompt(agent, sensory, discussion, actions_so_far or [])

    raw = chat(
        system=f"You are {agent.name} the {agent.agent_class} in a dungeon crawler. Output a single game command, nothing else.",
        message=prompt,
        model=AGENT_MODEL,
        max_tokens=100,
    )
    action = raw.split("\n")[0].strip()
    if action.startswith("/"):
        action = action[1:]
    return action


def parse_action(action: str) -> tuple[str, str]:
    """Returns (command, argument). Argument may be empty."""
    parts = action.strip().split(None, 1)
    if not parts:
        return ("say", "I'm not sure what to do.")
    cmd = parts[0].lower()
    arg = parts[1] if len(parts) > 1 else ""
    return (cmd, arg)
