import React from "react";
import { AgentSnapshot, AGENT_COLORS, RoomInfo } from "../types";

interface AgentPanelProps {
  agents: AgentSnapshot[];
  rooms: RoomInfo[];
}

function HealthBar({ value, max, color }: { value: number; max: number; color: string }) {
  const pct = max > 0 ? Math.max(0, Math.min(100, (value / max) * 100)) : 0;
  return (
    <div className="w-full h-2.5 bg-gray-800 rounded-full overflow-hidden">
      <div
        className="h-full rounded-full transition-all duration-300"
        style={{ width: `${pct}%`, backgroundColor: color }}
      />
    </div>
  );
}

export default function AgentPanel({ agents, rooms }: AgentPanelProps) {
  const roomMap = new Map(rooms.map((r) => [r.id, r]));

  return (
    <div className="flex gap-3">
      {agents.map((agent) => {
        const colors = AGENT_COLORS[agent.name] || AGENT_COLORS.Kael;
        const room = roomMap.get(agent.room_id);

        return (
          <div
            key={agent.name}
            className={`flex-1 rounded-lg border ${colors.border} ${colors.bg} p-3 ${!agent.alive ? "opacity-40" : ""}`}
          >
            {/* Header row: name + location */}
            <div className="flex items-center justify-between mb-1.5">
              <div className="flex items-center gap-2">
                <div className="w-3 h-3 rounded-full" style={{ backgroundColor: colors.primary }} />
                <span className={`font-bold text-sm ${colors.text}`}>{agent.name}</span>
              </div>
              <span className="text-xs text-gray-500">{room?.name || agent.room_id}</span>
              {!agent.alive && (
                <span className="text-xs text-red-400 font-semibold">DEAD</span>
              )}
            </div>

            {/* HP + MP side by side */}
            <div className="flex gap-3 mb-1.5">
              <div className="flex-1">
                <div className="flex justify-between text-xs mb-0.5">
                  <span className="text-gray-400">HP</span>
                  <span className="text-gray-300">{agent.hp}/{agent.max_hp}</span>
                </div>
                <HealthBar value={agent.hp} max={agent.max_hp} color="#ef4444" />
              </div>
              <div className="flex-1">
                <div className="flex justify-between text-xs mb-0.5">
                  <span className="text-gray-400">MP</span>
                  <span className="text-gray-300">{agent.mp}/{agent.max_mp}</span>
                </div>
                <HealthBar value={agent.mp} max={agent.max_mp} color="#3b82f6" />
              </div>
            </div>

            {/* Equipment + last action in compact row */}
            <div className="flex gap-4 text-xs text-gray-500">
              <span>{agent.weapon.name} <span className="text-amber-400">ATK:{agent.weapon.atk}</span></span>
              <span>{agent.armor.name} <span className="text-cyan-400">DEF:{agent.armor.pdef}</span></span>
              <span>{agent.ring.name} <span className="text-purple-400">MAG:{agent.ring.mdmg}</span></span>
            </div>
            {agent.last_action && (
              <div className="text-xs text-gray-500 mt-1 truncate">
                Last: <span className="text-gray-400">{agent.last_action}</span>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
