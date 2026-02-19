import React, { useEffect, useRef } from "react";
import { GameEventData, AGENT_COLORS } from "../types";

interface EventLogProps {
  events: GameEventData[];
}

function getEventColor(agent: string): string {
  const colors = AGENT_COLORS[agent];
  if (colors) return colors.text;
  if (agent === "poison") return "text-purple-400";
  if (agent === "system") return "text-amber-500";
  return "text-gray-400";
}

function getEventIcon(action: string): string {
  if (action.startsWith("move")) return "\u2192";
  if (action.startsWith("attack")) return "\u2694\ufe0f";
  if (action.startsWith("missile") || action.startsWith("fireball")) return "\u2728";
  if (action.startsWith("poison")) return "\u2620\ufe0f";
  if (action === "heal") return "\u2764\ufe0f";
  if (action === "look") return "\ud83d\udc41\ufe0f";
  if (action.startsWith("get")) return "\ud83c\udfaf";
  if (action.startsWith("tell") || action === "say") return "\ud83d\udcac";
  if (action === "think") return "\ud83d\udca1";
  if (action === "counterattack") return "\u26a1";
  if (action === "tick") return "\u2623\ufe0f";
  if (action === "system") return "\u2699\ufe0f";
  return "\u25b6";
}

export default function EventLog({ events }: EventLogProps) {
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [events]);

  return (
    <div className="bg-gray-900 rounded-lg border border-gray-800 p-2 sm:p-3 h-full overflow-y-auto">
      <div className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">
        Event Log
      </div>
      {events.length === 0 ? (
        <div className="text-sm text-gray-600 italic">No events yet</div>
      ) : (
        <div className="space-y-1">
          {events.map((event, i) => (
            <div key={i} className="flex items-start gap-2 text-sm">
              <span className="shrink-0 w-5 text-center">{getEventIcon(event.action)}</span>
              <span className={`font-semibold shrink-0 ${getEventColor(event.agent)}`}>
                {event.agent}
              </span>
              <span className={`break-words ${event.action === "think" ? "text-gray-500 italic" : "text-gray-400"}`}>
                {event.result.split("\n").map((line, j) => (
                  <span key={j}>
                    {j > 0 && <br />}
                    {line}
                  </span>
                ))}
              </span>
            </div>
          ))}
        </div>
      )}
      <div ref={endRef} />
    </div>
  );
}
