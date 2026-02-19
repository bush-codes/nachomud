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

export interface AgentSnapshot {
  name: string;
  hp: number;
  max_hp: number;
  mp: number;
  max_mp: number;
  room_id: string;
  alive: boolean;
  weapon: Item;
  armor: Item;
  ring: Item;
  last_action: string;
  last_result: string;
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

export type AgentColor = "red" | "blue" | "green";

export const AGENT_COLORS: Record<string, { primary: string; bg: string; text: string; dot: string; border: string }> = {
  Kael:  { primary: "#ef4444", bg: "bg-red-900/30",  text: "text-red-400",  dot: "#ef4444", border: "border-red-700" },
  Lyria: { primary: "#3b82f6", bg: "bg-blue-900/30", text: "text-blue-400", dot: "#3b82f6", border: "border-blue-700" },
  Finn:  { primary: "#22c55e", bg: "bg-green-900/30", text: "text-green-400", dot: "#22c55e", border: "border-green-700" },
};
