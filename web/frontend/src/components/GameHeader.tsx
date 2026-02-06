import React from "react";

interface GameHeaderProps {
  outcome: "victory" | "defeat" | "timeout" | null;
  totalTicks: number;
  currentTick: number;
  loading: boolean;
  onRunSimulation: () => void;
}

const BADGE_STYLES: Record<string, string> = {
  victory: "bg-emerald-600 text-emerald-100",
  defeat: "bg-red-600 text-red-100",
  timeout: "bg-amber-600 text-amber-100",
  running: "bg-blue-600 text-blue-100 animate-pulse",
  idle: "bg-gray-700 text-gray-300",
};

export default function GameHeader({ outcome, totalTicks, currentTick, loading, onRunSimulation }: GameHeaderProps) {
  let status: string;
  let badgeStyle: string;

  if (loading) {
    status = "Simulating...";
    badgeStyle = BADGE_STYLES.running;
  } else if (outcome) {
    status = outcome.charAt(0).toUpperCase() + outcome.slice(1);
    badgeStyle = BADGE_STYLES[outcome];
  } else {
    status = "Ready";
    badgeStyle = BADGE_STYLES.idle;
  }

  return (
    <header className="flex items-center justify-between px-6 py-3 bg-gray-900 border-b border-gray-800">
      <div className="flex items-center gap-4">
        <h1 className="text-xl font-bold tracking-wide text-gray-100">
          <span className="text-amber-400">Nacho</span>MUD
          <span className="text-sm font-normal text-gray-500 ml-2">Simulation Viewer</span>
        </h1>
        <span className={`px-3 py-1 rounded-full text-xs font-semibold uppercase tracking-wider ${badgeStyle}`}>
          {status}
        </span>
        {outcome && (
          <span className="text-sm text-gray-500">
            Tick {currentTick} / {totalTicks}
          </span>
        )}
      </div>
      <button
        onClick={onRunSimulation}
        disabled={loading}
        className="px-4 py-2 bg-amber-600 hover:bg-amber-500 disabled:bg-gray-700 disabled:text-gray-500 text-white text-sm font-semibold rounded transition-colors"
      >
        {loading ? (
          <span className="flex items-center gap-2">
            <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
            Running...
          </span>
        ) : (
          "Run Simulation"
        )}
      </button>
    </header>
  );
}
