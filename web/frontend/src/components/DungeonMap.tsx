import React, { useMemo } from "react";
import { RoomInfo, AgentSnapshot, RoomSnapshot, AGENT_COLORS } from "../types";

interface DungeonMapProps {
  rooms: RoomInfo[];
  agentStates: AgentSnapshot[];
  roomStates: Record<string, RoomSnapshot>;
}

const ROOM_W = 130;
const ROOM_H = 44;
const GRID_X = 170; // horizontal spacing between grid cells
const GRID_Y = 80;  // vertical spacing between grid cells

// Direction offsets on the grid: n=up (negative y), s=down, e=right, w=left
const DIR_OFFSET: Record<string, { dx: number; dy: number }> = {
  n: { dx: 0, dy: -1 },
  s: { dx: 0, dy: 1 },
  e: { dx: 1, dy: 0 },
  w: { dx: -1, dy: 0 },
};

function computeRoomPositions(rooms: RoomInfo[]): Record<string, { x: number; y: number }> {
  if (rooms.length === 0) return {};

  const roomMap = new Map(rooms.map((r) => [r.id, r]));
  const gridPos: Record<string, { gx: number; gy: number }> = {};
  const occupied = new Map<string, string>(); // "gx,gy" -> room_id

  // BFS from room_1 (or first room)
  const startId = roomMap.has("room_1") ? "room_1" : rooms[0].id;
  const queue: string[] = [startId];
  gridPos[startId] = { gx: 0, gy: 0 };
  occupied.set("0,0", startId);

  while (queue.length > 0) {
    const currentId = queue.shift()!;
    const current = roomMap.get(currentId);
    if (!current) continue;
    const { gx, gy } = gridPos[currentId];

    for (const [dir, targetId] of Object.entries(current.exits)) {
      if (gridPos[targetId] !== undefined) continue; // already placed
      if (!roomMap.has(targetId)) continue;

      const offset = DIR_OFFSET[dir];
      if (!offset) continue;

      let nx = gx + offset.dx;
      let ny = gy + offset.dy;

      // If cell is occupied, try shifting further in the same direction
      let attempts = 0;
      while (occupied.has(`${nx},${ny}`) && attempts < 5) {
        nx += offset.dx;
        ny += offset.dy;
        attempts++;
      }

      // If still occupied, try perpendicular offsets
      if (occupied.has(`${nx},${ny}`)) {
        const perpDirs = offset.dx === 0 ? [{ dx: 1, dy: 0 }, { dx: -1, dy: 0 }] : [{ dx: 0, dy: 1 }, { dx: 0, dy: -1 }];
        let placed = false;
        for (const perp of perpDirs) {
          const testX = gx + offset.dx + perp.dx;
          const testY = gy + offset.dy + perp.dy;
          if (!occupied.has(`${testX},${testY}`)) {
            nx = testX;
            ny = testY;
            placed = true;
            break;
          }
        }
        if (!placed) {
          // Last resort: find nearest empty cell
          for (let r = 1; r <= 10; r++) {
            let found = false;
            for (let dx = -r; dx <= r && !found; dx++) {
              for (let dy = -r; dy <= r && !found; dy++) {
                if (Math.abs(dx) !== r && Math.abs(dy) !== r) continue;
                const testX = gx + offset.dx + dx;
                const testY = gy + offset.dy + dy;
                if (!occupied.has(`${testX},${testY}`)) {
                  nx = testX;
                  ny = testY;
                  found = true;
                }
              }
            }
            if (found) break;
          }
        }
      }

      gridPos[targetId] = { gx: nx, gy: ny };
      occupied.set(`${nx},${ny}`, targetId);
      queue.push(targetId);
    }
  }

  // Place any rooms not reached by BFS (disconnected)
  for (const room of rooms) {
    if (gridPos[room.id] === undefined) {
      let fx = 0, fy = 0;
      while (occupied.has(`${fx},${fy}`)) fx++;
      gridPos[room.id] = { gx: fx, gy: fy };
      occupied.set(`${fx},${fy}`, room.id);
    }
  }

  // Convert grid coordinates to pixel positions
  const positions: Record<string, { x: number; y: number }> = {};
  for (const [id, { gx, gy }] of Object.entries(gridPos)) {
    positions[id] = { x: gx * GRID_X, y: gy * GRID_Y };
  }

  return positions;
}

function getRoomColor(room: RoomInfo, roomState: RoomSnapshot | undefined): string {
  const hasBoss = room.mobs.some((m) => m.is_boss);
  const livingMobs = roomState
    ? roomState.mobs.filter((m) => m.hp > 0)
    : room.mobs.filter((m) => m.hp > 0);

  if (hasBoss && livingMobs.length > 0) return "#4a1942";
  if (livingMobs.length > 0) return "#3b1a1a";
  if (room.npcs.length > 0) return "#1a2e1a";
  return "#1e1e2e";
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
  const positions = useMemo(() => computeRoomPositions(rooms), [rooms]);

  // Compute viewBox from bounding box of all positions
  const viewBox = useMemo(() => {
    const posValues = Object.values(positions);
    if (posValues.length === 0) return "-10 -10 450 600";
    const xs = posValues.map((p) => p.x);
    const ys = posValues.map((p) => p.y);
    const minX = Math.min(...xs) - 20;
    const minY = Math.min(...ys) - 20;
    const maxX = Math.max(...xs) + ROOM_W + 20;
    const maxY = Math.max(...ys) + ROOM_H + 20;
    return `${minX} ${minY} ${maxX - minX} ${maxY - minY}`;
  }, [positions]);

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
    <div className="h-full overflow-hidden bg-gray-950 rounded-lg border border-gray-800 p-2">
      <svg viewBox={viewBox} className="w-full h-full">
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
          const fp = positions[from];
          const tp = positions[to];
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
          const pos = positions[room.id];
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
