import React from "react";

const OLLAMA_MODELS = [
  "gemma3:4b",
  "gemma3:12b",
  "qwen2.5:7b",
  "llama3.1:8b",
  "gemma2:9b",
  "mistral:7b",
  "phi4:14b",
  "llama3.2:3b",
  "deepseek-r1:14b",
];

interface GameHeaderProps {
  outcome: "victory" | "defeat" | "timeout" | null;
  loading: boolean;
  currentTick: number;
  maxTicks: number;
  agentModel: string;
  onMaxTicksChange: (value: number) => void;
  onAgentModelChange: (value: string) => void;
  onRunSimulation: () => void;
  onResetSimulation: () => void;
}

const BADGE_STYLES: Record<string, string> = {
  victory: "bg-emerald-600 text-emerald-100",
  defeat: "bg-red-600 text-red-100",
  timeout: "bg-amber-600 text-amber-100",
  running: "bg-blue-600 text-blue-100 animate-pulse",
  idle: "bg-gray-700 text-gray-300",
};

export default function GameHeader({ outcome, loading, currentTick, maxTicks, agentModel, onMaxTicksChange, onAgentModelChange, onRunSimulation, onResetSimulation }: GameHeaderProps) {
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
    <header className="flex flex-wrap items-center justify-between gap-2 px-3 sm:px-6 py-2 sm:py-3 bg-gray-900 border-b border-gray-800">
      <div className="flex flex-wrap items-center gap-2 sm:gap-4">
        <h1 className="text-base sm:text-xl font-bold tracking-wide text-gray-100">
          <span className="text-amber-400">Nacho</span>MUD
          <span className="hidden sm:inline text-sm font-normal text-gray-500 ml-2">Simulation Viewer</span>
        </h1>
        <span className={`px-2 sm:px-3 py-0.5 sm:py-1 rounded-full text-xs font-semibold uppercase tracking-wider ${badgeStyle}`}>
          {status}
        </span>
        {(loading || currentTick > 0) && (
          <span className="text-xs sm:text-sm text-gray-400 font-mono">
            Tick {currentTick}
          </span>
        )}
      </div>
      <div className="flex items-center gap-2 sm:gap-3">
        <label className="flex items-center gap-1.5 text-xs sm:text-sm text-gray-400">
          Model
          <select
            value={agentModel}
            onChange={(e) => onAgentModelChange(e.target.value)}
            disabled={loading}
            className="px-1.5 py-1 sm:py-1.5 bg-gray-800 border border-gray-700 rounded text-gray-200 text-xs sm:text-sm disabled:opacity-50"
          >
            {OLLAMA_MODELS.map((m) => (
              <option key={m} value={m}>{m}</option>
            ))}
          </select>
        </label>
        <label className="flex items-center gap-1.5 text-xs sm:text-sm text-gray-400">
          Ticks
          <input
            type="number"
            min={1}
            max={200}
            value={maxTicks}
            onChange={(e) => onMaxTicksChange(Math.max(1, Math.min(200, Number(e.target.value) || 1)))}
            disabled={loading}
            className="w-14 sm:w-16 px-1.5 py-1 sm:py-1.5 bg-gray-800 border border-gray-700 rounded text-gray-200 text-xs sm:text-sm text-center disabled:opacity-50"
          />
        </label>
        <button
          onClick={onResetSimulation}
          className="px-3 sm:px-4 py-1.5 sm:py-2 bg-red-700 hover:bg-red-600 text-white text-xs sm:text-sm font-semibold rounded transition-colors"
        >
          Reset
        </button>
        <button
          onClick={onRunSimulation}
          disabled={loading}
          className="px-3 sm:px-4 py-1.5 sm:py-2 bg-amber-600 hover:bg-amber-500 disabled:bg-gray-700 disabled:text-gray-500 text-white text-xs sm:text-sm font-semibold rounded transition-colors"
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
      </div>
    </header>
  );
}
