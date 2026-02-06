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
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2 sm:gap-3">
      {agents.map((agent) => {
        const colors = AGENT_COLORS[agent.name] || AGENT_COLORS.Kael;
        const room = roomMap.get(agent.room_id);

        return (
          <div
            key={agent.name}
            className={`rounded-lg border ${colors.border} ${colors.bg} p-2 sm:p-3 min-w-0 ${!agent.alive ? "opacity-40" : ""}`}
          >
            {/* Header row: name + location */}
            <div className="flex items-center justify-between mb-1.5 min-w-0">
              <div className="flex items-center gap-1.5 sm:gap-2 min-w-0">
                <div className="w-2.5 sm:w-3 h-2.5 sm:h-3 rounded-full shrink-0" style={{ backgroundColor: colors.primary }} />
                <span className={`font-bold text-xs sm:text-sm ${colors.text} truncate`}>{agent.name}</span>
              </div>
              <span className="text-xs text-gray-500 truncate ml-2 shrink-0">{room?.name || agent.room_id}</span>
              {!agent.alive && (
                <span className="text-xs text-red-400 font-semibold shrink-0 ml-1">DEAD</span>
              )}
            </div>

            {/* HP + MP side by side */}
            <div className="flex gap-2 sm:gap-3 mb-1.5">
              <div className="flex-1 min-w-0">
                <div className="flex justify-between text-xs mb-0.5">
                  <span className="text-gray-400">HP</span>
                  <span className="text-gray-300">{agent.hp}/{agent.max_hp}</span>
                </div>
                <HealthBar value={agent.hp} max={agent.max_hp} color="#ef4444" />
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex justify-between text-xs mb-0.5">
                  <span className="text-gray-400">MP</span>
                  <span className="text-gray-300">{agent.mp}/{agent.max_mp}</span>
                </div>
                <HealthBar value={agent.mp} max={agent.max_mp} color="#3b82f6" />
              </div>
            </div>

            {/* Equipment + last action in compact row */}
            <div className="flex flex-wrap gap-x-3 gap-y-0.5 text-xs text-gray-500">
              <span className="whitespace-nowrap">{agent.weapon.name} <span className="text-amber-400">ATK:{agent.weapon.atk}</span></span>
              <span className="whitespace-nowrap">{agent.armor.name} <span className="text-cyan-400">DEF:{agent.armor.pdef}</span></span>
              <span className="whitespace-nowrap">{agent.ring.name} <span className="text-purple-400">MAG:{agent.ring.mdmg}</span></span>
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
