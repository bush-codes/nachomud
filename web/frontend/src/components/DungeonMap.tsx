import React from "react";
import { RoomInfo, AgentSnapshot, RoomSnapshot, AGENT_COLORS } from "../types";

interface DungeonMapProps {
  rooms: RoomInfo[];
  agentStates: AgentSnapshot[];
  roomStates: Record<string, RoomSnapshot>;
}

// Manual layout for the 15-room dungeon topology
// Based on world.json exits:
// room_1 -> n -> room_2
// room_2 -> e -> room_3, n -> room_4
// room_4 -> e -> room_5, n -> room_6
// room_6 -> e -> room_7, n -> room_8
// room_7 -> n -> room_9
// room_8 -> e -> room_9, n -> room_10
// room_9 -> n -> room_11
// room_10 -> n -> room_12
// room_11 -> n -> room_13
// room_12 -> e -> room_13, n -> room_14
// room_13 -> n -> room_14
// room_14 -> n -> room_15

const ROOM_W = 130;
const ROOM_H = 44;

const ROOM_POSITIONS: Record<string, { x: number; y: number }> = {
  room_1:  { x: 100, y: 550 },
  room_2:  { x: 100, y: 460 },
  room_3:  { x: 270, y: 460 },
  room_4:  { x: 100, y: 370 },
  room_5:  { x: 270, y: 370 },
  room_6:  { x: 100, y: 280 },
  room_7:  { x: 270, y: 280 },
  room_8:  { x: 100, y: 190 },
  room_9:  { x: 270, y: 190 },
  room_10: { x: 100, y: 100 },
  room_11: { x: 270, y: 100 },
  room_12: { x: 100, y: 10 },
  room_13: { x: 270, y: 10 },
  room_14: { x: 185, y: -70 },
  room_15: { x: 185, y: -150 },
};

function getRoomColor(room: RoomInfo, roomState: RoomSnapshot | undefined): string {
  // Boss room
  const hasBoss = room.mobs.some((m) => m.is_boss);
  const livingMobs = roomState
    ? roomState.mobs.filter((m) => m.hp > 0)
    : room.mobs.filter((m) => m.hp > 0);

  if (hasBoss && livingMobs.length > 0) return "#4a1942"; // purple glow for boss
  if (livingMobs.length > 0) return "#3b1a1a"; // red tint for danger
  if (room.npcs.length > 0) return "#1a2e1a"; // green tint for NPCs
  return "#1e1e2e"; // dark visited
}

function getRoomBorder(room: RoomInfo, roomState: RoomSnapshot | undefined): string {
  const hasBoss = room.mobs.some((m) => m.is_boss);
  const livingMobs = roomState
    ? roomState.mobs.filter((m) => m.hp > 0)
    : room.mobs.filter((m) => m.hp > 0);

  if (hasBoss && livingMobs.length > 0) return "#9333ea";
  if (livingMobs.length > 0) return "#991b1b";
  return "#374151";
}

export default function DungeonMap({ rooms, agentStates, roomStates }: DungeonMapProps) {
  const roomMap = new Map(rooms.map((r) => [r.id, r]));

  // Collect all edges
  const edges: { from: string; to: string }[] = [];
  const seen = new Set<string>();
  for (const room of rooms) {
    for (const targetId of Object.values(room.exits)) {
      const key = [room.id, targetId].sort().join("-");
      if (!seen.has(key)) {
        seen.add(key);
        edges.push({ from: room.id, to: targetId });
      }
    }
  }

  // Agent positions per room
  const agentsByRoom = new Map<string, AgentSnapshot[]>();
  for (const agent of agentStates) {
    if (!agent.alive) continue;
    const list = agentsByRoom.get(agent.room_id) || [];
    list.push(agent);
    agentsByRoom.set(agent.room_id, list);
  }

  return (
    <div className="flex-1 overflow-auto bg-gray-950 rounded-lg border border-gray-800 p-4">
      <svg viewBox="-10 -180 450 780" className="w-full h-full" style={{ minHeight: 400 }}>
        <defs>
          <filter id="glow">
            <feGaussianBlur stdDeviation="3" result="coloredBlur" />
            <feMerge>
              <feMergeNode in="coloredBlur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>

        {/* Draw edges */}
        {edges.map(({ from, to }) => {
          const fp = ROOM_POSITIONS[from];
          const tp = ROOM_POSITIONS[to];
          if (!fp || !tp) return null;
          return (
            <line
              key={`${from}-${to}`}
              x1={fp.x + ROOM_W / 2}
              y1={fp.y + ROOM_H / 2}
              x2={tp.x + ROOM_W / 2}
              y2={tp.y + ROOM_H / 2}
              stroke="#374151"
              strokeWidth={2}
            />
          );
        })}

        {/* Draw rooms */}
        {rooms.map((room) => {
          const pos = ROOM_POSITIONS[room.id];
          if (!pos) return null;
          const rs = roomStates[room.id];
          const fill = getRoomColor(room, rs);
          const border = getRoomBorder(room, rs);
          const agents = agentsByRoom.get(room.id) || [];
          const livingMobs = rs
            ? rs.mobs.filter((m) => m.hp > 0)
            : room.mobs.filter((m) => m.hp > 0);
          const hasBoss = room.mobs.some((m) => m.is_boss);

          return (
            <g key={room.id}>
              <rect
                x={pos.x}
                y={pos.y}
                width={ROOM_W}
                height={ROOM_H}
                rx={6}
                fill={fill}
                stroke={border}
                strokeWidth={agents.length > 0 ? 2.5 : 1.5}
                filter={hasBoss && livingMobs.length > 0 ? "url(#glow)" : undefined}
              />
              {/* Room name */}
              <text
                x={pos.x + ROOM_W / 2}
                y={pos.y + 16}
                textAnchor="middle"
                fill="#d1d5db"
                fontSize={10}
                fontWeight="bold"
              >
                {room.name.length > 18 ? room.name.slice(0, 16) + "..." : room.name}
              </text>
              {/* Mob count or cleared indicator */}
              <text
                x={pos.x + ROOM_W / 2}
                y={pos.y + 30}
                textAnchor="middle"
                fill={livingMobs.length > 0 ? "#f87171" : "#4ade80"}
                fontSize={8}
              >
                {livingMobs.length > 0
                  ? `${livingMobs.length} mob${livingMobs.length > 1 ? "s" : ""}`
                  : room.mobs.length > 0
                    ? "cleared"
                    : room.npcs.length > 0
                      ? "NPC"
                      : "safe"}
              </text>
              {/* Agent dots */}
              {agents.map((agent, i) => {
                const color = AGENT_COLORS[agent.name]?.dot || "#fff";
                const dotX = pos.x + ROOM_W / 2 + (i - (agents.length - 1) / 2) * 14;
                const dotY = pos.y + 40;
                return (
                  <circle
                    key={agent.name}
                    cx={dotX}
                    cy={dotY}
                    r={5}
                    fill={color}
                    stroke="#000"
                    strokeWidth={1}
                  />
                );
              })}
            </g>
          );
        })}
      </svg>
    </div>
  );
}
