import React from "react";
import { AgentSnapshot, AGENT_COLORS, RoomInfo } from "../types";

interface AgentPanelProps {
  agents: AgentSnapshot[];
  rooms: RoomInfo[];
}

function HealthBar({ value, max, color }: { value: number; max: number; color: string }) {
  const pct = max > 0 ? Math.max(0, Math.min(100, (value / max) * 100)) : 0;
  return (
    <div className="w-full h-3 bg-gray-800 rounded-full overflow-hidden">
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
    <div className="flex flex-col gap-3 w-72 shrink-0">
      {agents.map((agent) => {
        const colors = AGENT_COLORS[agent.name] || AGENT_COLORS.Kael;
        const room = roomMap.get(agent.room_id);

        return (
          <div
            key={agent.name}
            className={`rounded-lg border ${colors.border} ${colors.bg} p-3 ${!agent.alive ? "opacity-40" : ""}`}
          >
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center gap-2">
                <div className="w-3 h-3 rounded-full" style={{ backgroundColor: colors.primary }} />
                <span className={`font-bold text-sm ${colors.text}`}>{agent.name}</span>
              </div>
              {!agent.alive && (
                <span className="text-xs text-red-400 font-semibold">DEAD</span>
              )}
            </div>

            {/* HP */}
            <div className="mb-1">
              <div className="flex justify-between text-xs mb-0.5">
                <span className="text-gray-400">HP</span>
                <span className="text-gray-300">{agent.hp}/{agent.max_hp}</span>
              </div>
              <HealthBar value={agent.hp} max={agent.max_hp} color="#ef4444" />
            </div>

            {/* MP */}
            <div className="mb-2">
              <div className="flex justify-between text-xs mb-0.5">
                <span className="text-gray-400">MP</span>
                <span className="text-gray-300">{agent.mp}/{agent.max_mp}</span>
              </div>
              <HealthBar value={agent.mp} max={agent.max_mp} color="#3b82f6" />
            </div>

            {/* Equipment */}
            <div className="text-xs text-gray-500 space-y-0.5">
              <div className="flex justify-between">
                <span>Weapon</span>
                <span className="text-gray-300">{agent.weapon.name} <span className="text-amber-400">ATK:{agent.weapon.atk}</span></span>
              </div>
              <div className="flex justify-between">
                <span>Armor</span>
                <span className="text-gray-300">{agent.armor.name} <span className="text-cyan-400">DEF:{agent.armor.pdef}</span></span>
              </div>
              <div className="flex justify-between">
                <span>Ring</span>
                <span className="text-gray-300">{agent.ring.name} <span className="text-purple-400">MAG:{agent.ring.mdmg}</span></span>
              </div>
            </div>

            {/* Location */}
            <div className="mt-2 pt-2 border-t border-gray-700/50">
              <div className="text-xs text-gray-500">
                Location: <span className="text-gray-300">{room?.name || agent.room_id}</span>
              </div>
              {agent.last_action && (
                <div className="text-xs text-gray-500 mt-0.5 truncate">
                  Last: <span className="text-gray-400">{agent.last_action}</span>
                </div>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}
