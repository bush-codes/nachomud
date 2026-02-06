from __future__ import annotations

import json

from config import NARRATOR_MODEL
from llm import chat
from models import Room

SYSTEM_PROMPT = """You are the narrator of Aeldrath, a high-fantasy world where a Shadowfell Rift has torn open beneath the ancient fortress of Durnhollow. Dark creatures pour from the rift, corrupting the land. Three heroes have been summoned to descend into the fortress, fight through its depths, and close the rift before it consumes the realm.

Your tone is atmospheric, vivid, and concise. Describe environments with sensory detail. Keep descriptions to 2-3 sentences. You are a dungeon master narrating events as they unfold."""


def generate_room_description(room_name: str, room_context: str) -> str:
    return chat(
        system=SYSTEM_PROMPT,
        message=f"Write a 2-3 sentence atmospheric description for a dungeon room called '{room_name}'. Context: {room_context}. Be vivid and concise.",
        model=NARRATOR_MODEL,
        max_tokens=200,
    )


def narrate_combat(agent_name: str, action: str, result: str) -> str:
    return chat(
        system=SYSTEM_PROMPT,
        message=f"Write a brief, dramatic one-sentence narration for this combat event:\nAgent: {agent_name}\nAction: {action}\nResult: {result}",
        model=NARRATOR_MODEL,
        max_tokens=150,
    )


def narrate_npc_dialogue(npc_name: str, npc_title: str, dialogue_hints: list[str], agent_name: str) -> str:
    hints = "; ".join(dialogue_hints) if dialogue_hints else "mysterious, cryptic"
    return chat(
        system=SYSTEM_PROMPT,
        message=f"{agent_name} speaks with {npc_name} the {npc_title}. Dialogue themes: {hints}. Write 1-2 sentences of what {npc_name} says in-character. Use quotes.",
        model=NARRATOR_MODEL,
        max_tokens=150,
    )


def generate_world_json() -> dict:
    prompt = """Generate a dungeon for Durnhollow fortress as JSON. Requirements:
- Exactly 15 rooms with unique IDs like "room_1", "room_2", etc.
- Room "room_1" is the entrance (Entry Chamber)
- Room "room_15" is the final boss room (The Shadowfell Rift)
- Each room has: id, name, exits (dict of direction -> room_id, using n/s/e/w)
- Exits must be bidirectional (if room_1 has n->room_2, room_2 must have s->room_1)
- Mobs get harder deeper in (weak goblins near entrance, undead/demons near rift)
- Each mob has: name, hp, max_hp, atk, mdef (0 for most, some for special), is_boss (true only for final boss)
- The final boss should have: hp 30, max_hp 30, atk 6, mdef 2, is_boss true
- Include optional loot on some mobs: items with name, slot (weapon/armor/ring), and stat bonuses
- Place 2-3 NPCs in early/mid rooms with: name, title, dialogue (list of theme strings)
- One NPC should give an item (include "item" field with name, slot, and stats)
- Some rooms should have no mobs (safe rooms, corridors)

Return ONLY valid JSON with this structure:
{
  "rooms": [
    {
      "id": "room_1",
      "name": "Entry Chamber",
      "exits": {"n": "room_2"},
      "mobs": [{"name": "Goblin Scout", "hp": 4, "max_hp": 4, "atk": 2, "mdef": 0, "is_boss": false, "loot": []}],
      "npcs": [],
      "items": []
    }
  ]
}"""

    text = chat(
        system="You are a game designer. Output ONLY valid JSON, no markdown, no explanation.",
        message=prompt,
        model=NARRATOR_MODEL,
        max_tokens=4096,
    )
    # Strip markdown code fences if present
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines)
    return json.loads(text)
