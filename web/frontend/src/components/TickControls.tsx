import React from "react";

interface TickControlsProps {
  currentTick: number;
  totalTicks: number;
  playing: boolean;
  speed: number;
  onSetTick: (tick: number) => void;
  onTogglePlay: () => void;
  onSetSpeed: (speed: number) => void;
}

const SPEEDS = [0.5, 1, 2, 5];

export default function TickControls({
  currentTick,
  totalTicks,
  playing,
  speed,
  onSetTick,
  onTogglePlay,
  onSetSpeed,
}: TickControlsProps) {
  const disabled = totalTicks === 0;

  return (
    <div className="flex flex-wrap items-center gap-2 sm:gap-4 px-2 sm:px-4 py-2 bg-gray-900 rounded-lg border border-gray-800">
      {/* Transport controls */}
      <div className="flex items-center gap-0.5 sm:gap-1">
        <button
          onClick={() => onSetTick(1)}
          disabled={disabled}
          className="px-1.5 sm:px-2 py-1 text-xs sm:text-sm text-gray-300 hover:text-white hover:bg-gray-700 rounded disabled:opacity-30 disabled:cursor-not-allowed"
          title="Jump to start"
        >
          |&lt;
        </button>
        <button
          onClick={() => onSetTick(Math.max(1, currentTick - 1))}
          disabled={disabled}
          className="px-1.5 sm:px-2 py-1 text-xs sm:text-sm text-gray-300 hover:text-white hover:bg-gray-700 rounded disabled:opacity-30 disabled:cursor-not-allowed"
          title="Previous tick"
        >
          &lt;
        </button>
        <button
          onClick={onTogglePlay}
          disabled={disabled}
          className="px-2 sm:px-3 py-1 text-xs sm:text-sm font-bold text-gray-300 hover:text-white hover:bg-gray-700 rounded disabled:opacity-30 disabled:cursor-not-allowed min-w-[32px] sm:min-w-[40px]"
          title={playing ? "Pause" : "Play"}
        >
          {playing ? "| |" : "\u25b6"}
        </button>
        <button
          onClick={() => onSetTick(Math.min(totalTicks, currentTick + 1))}
          disabled={disabled}
          className="px-1.5 sm:px-2 py-1 text-xs sm:text-sm text-gray-300 hover:text-white hover:bg-gray-700 rounded disabled:opacity-30 disabled:cursor-not-allowed"
          title="Next tick"
        >
          &gt;
        </button>
        <button
          onClick={() => onSetTick(totalTicks)}
          disabled={disabled}
          className="px-1.5 sm:px-2 py-1 text-xs sm:text-sm text-gray-300 hover:text-white hover:bg-gray-700 rounded disabled:opacity-30 disabled:cursor-not-allowed"
          title="Jump to end"
        >
          &gt;|
        </button>
      </div>

      {/* Tick slider */}
      <div className="flex-1 flex items-center gap-2 sm:gap-3 min-w-0">
        <span className="text-xs text-gray-500 font-mono w-20 sm:w-24 text-center shrink-0">
          Tick {currentTick} / {totalTicks || "-"}
        </span>
        <input
          type="range"
          min={1}
          max={Math.max(1, totalTicks)}
          value={currentTick}
          onChange={(e) => onSetTick(Number(e.target.value))}
          disabled={disabled}
          className="flex-1 h-1.5 bg-gray-700 rounded-full appearance-none cursor-pointer accent-amber-500 disabled:opacity-30 min-w-0"
        />
      </div>

      {/* Speed control */}
      <div className="flex items-center gap-0.5 sm:gap-1">
        <span className="text-xs text-gray-500 mr-1">Speed:</span>
        {SPEEDS.map((s) => (
          <button
            key={s}
            onClick={() => onSetSpeed(s)}
            className={`px-1.5 sm:px-2 py-0.5 text-xs rounded ${
              speed === s
                ? "bg-amber-600 text-white"
                : "text-gray-400 hover:text-white hover:bg-gray-700"
            }`}
          >
            {s}x
          </button>
        ))}
      </div>
    </div>
  );
}
