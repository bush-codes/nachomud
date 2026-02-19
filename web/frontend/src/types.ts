export interface WorldInfo {
  id: string;
  name: string;
  description: string;
}

export interface Item {
  name: string;
  slot: string;
  atk: number;
  pdef: number;
  mdef: number;
  mdmg: number;
}

export interface MobInfo {
  name: string;
  hp: number;
  max_hp: number;
  atk: number;
  mdef: number;
  is_boss: boolean;
  loot?: Item[];
}

export interface NpcInfo {
  name: string;
  title: string;
}

export interface RoomInfo {
  id: string;
  name: string;
  description: string;
  exits: Record<string, string>;
  mobs: MobInfo[];
  npcs: NpcInfo[];
  items: Item[];
}

export interface AgentInfo {
  name: string;
  agent_class: string;
  personality: string;
  max_hp: number;
  max_mp: number;
  weapon: Item;
  armor: Item;
  ring: Item;
}

export interface StatusEffectInfo {
  name: string;
  remaining_ticks: number;
  value: number;
}

export interface AgentSnapshot {
  name: string;
  agent_class: string;
  hp: number;
  max_hp: number;
  mp: number;
  max_mp: number;
  ap: number;
  max_ap: number;
  speed: number;
  room_id: string;
  alive: boolean;
  weapon: Item;
  armor: Item;
  ring: Item;
  last_action: string;
  last_result: string;
  status_effects: StatusEffectInfo[];
}

export interface GameEventData {
  agent: string;
  action: string;
  result: string;
  room_id: string;
}

export interface RoomSnapshot {
  mobs: { name: string; hp: number; max_hp: number }[];
  items: Item[];
}

export interface SimulationResult {
  outcome: "victory" | "defeat" | "timeout";
  total_ticks: number;
  world: { rooms: RoomInfo[] };
  agents: AgentInfo[];
}

export interface ClassDefinition {
  hp: number;
  resource_type: "mp" | "ap";
  resource_max: number;
  speed: number;
  abilities: string[];
  default_name: string;
  personality: string;
}

// Class-based colors (used for all agent display)
export const CLASS_COLORS: Record<string, { primary: string; bg: string; text: string; dot: string; border: string }> = {
  Warrior: { primary: "#ef4444", bg: "bg-red-900/30",    text: "text-red-400",    dot: "#ef4444", border: "border-red-700" },
  Paladin: { primary: "#f59e0b", bg: "bg-amber-900/30",  text: "text-amber-400",  dot: "#f59e0b", border: "border-amber-700" },
  Mage:    { primary: "#3b82f6", bg: "bg-blue-900/30",   text: "text-blue-400",   dot: "#3b82f6", border: "border-blue-700" },
  Cleric:  { primary: "#9ca3af", bg: "bg-gray-700/30",   text: "text-gray-300",   dot: "#9ca3af", border: "border-gray-600" },
  Ranger:  { primary: "#22c55e", bg: "bg-green-900/30",  text: "text-green-400",  dot: "#22c55e", border: "border-green-700" },
  Rogue:   { primary: "#a855f7", bg: "bg-purple-900/30", text: "text-purple-400", dot: "#a855f7", border: "border-purple-700" },
};

// Legacy name-based colors (maps agent names to their class color)
export const AGENT_COLORS: Record<string, { primary: string; bg: string; text: string; dot: string; border: string }> = {
  Kael:   CLASS_COLORS.Warrior,
  Aldric: CLASS_COLORS.Paladin,
  Lyria:  CLASS_COLORS.Mage,
  Sera:   CLASS_COLORS.Cleric,
  Finn:   CLASS_COLORS.Ranger,
  Shade:  CLASS_COLORS.Rogue,
};

export function getAgentColor(agent: { name: string; agent_class?: string }) {
  // Prefer class-based color, fall back to name-based
  if (agent.agent_class && CLASS_COLORS[agent.agent_class]) {
    return CLASS_COLORS[agent.agent_class];
  }
  return AGENT_COLORS[agent.name] || CLASS_COLORS.Warrior;
}
