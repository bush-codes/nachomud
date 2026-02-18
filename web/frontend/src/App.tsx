import React, { useState, useEffect, useCallback, useRef } from "react";
import { SimulationResult, AgentSnapshot, GameEventData, RoomInfo, TickData } from "./types";
import GameHeader from "./components/GameHeader";
import DungeonMap from "./components/DungeonMap";
import AgentPanel from "./components/AgentPanel";
import EventLog from "./components/EventLog";
import TickControls from "./components/TickControls";

export default function App() {
  const [simulation, setSimulation] = useState<SimulationResult | null>(null);
  const [worldRooms, setWorldRooms] = useState<RoomInfo[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [currentTick, setCurrentTick] = useState(1);
  const [playing, setPlaying] = useState(false);
  const [liveFollow, setLiveFollow] = useState(true);
  const [speed, setSpeed] = useState(1);
  const [liveEvents, setLiveEvents] = useState<GameEventData[]>([]);
  const [liveTick, setLiveTick] = useState(0);
  const intervalRef = useRef<number | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  // Load the static world map on mount
  useEffect(() => {
    fetch("/api/world")
      .then((res) => res.json())
      .then((data) => setWorldRooms(data.rooms ?? []))
      .catch(() => {});
  }, []);

  const resetSimulation = useCallback(() => {
    if (abortRef.current) {
      abortRef.current.abort();
      abortRef.current = null;
    }
    setSimulation(null);
    setLoading(false);
    setPlaying(false);
    setLiveFollow(true);
    setCurrentTick(1);
    setError(null);
    setLiveEvents([]);
    setLiveTick(0);
  }, []);

  const runSimulation = useCallback(async () => {
    // Abort any previous run
    if (abortRef.current) {
      abortRef.current.abort();
    }
    const controller = new AbortController();
    abortRef.current = controller;

    setLoading(true);
    setPlaying(false);
    setLiveFollow(true);
    setSimulation(null);
    setError(null);

    try {
      const res = await fetch("/api/simulate", { method: "POST", signal: controller.signal });
      if (!res.ok) {
        const body = await res.json().catch(() => null);
        throw new Error(body?.detail || `Server error: ${res.status}`);
      }

      const reader = res.body!.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      let world: { rooms: RoomInfo[] } = { rooms: [] };
      let agents: SimulationResult["agents"] = [];
      const ticks: TickData[] = [];
      let outcome: SimulationResult["outcome"] | null = null;

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop()!;

        for (const line of lines) {
          if (!line.trim()) continue;
          const msg = JSON.parse(line);

          if (msg.type === "init") {
            world = msg.world;
            agents = msg.agents;
            setSimulation({
              outcome: "timeout",
              total_ticks: 0,
              world,
              agents,
              ticks: [],
            });
          } else if (msg.type === "event") {
            setLiveTick(msg.tick);
            setLiveEvents((prev) => [...prev, msg.event]);
          } else if (msg.type === "tick") {
            ticks.push({
              tick: msg.tick,
              events: msg.events,
              agent_states: msg.agent_states,
              room_states: msg.room_states,
            });
            setLiveEvents([]);
            setLiveTick(0);
            setSimulation({
              outcome: outcome ?? "timeout",
              total_ticks: ticks.length,
              world,
              agents,
              ticks: [...ticks],
            });
            // Only auto-advance if user hasn't paused
            setLiveFollow((live) => {
              if (live) setCurrentTick(ticks.length);
              return live;
            });
          } else if (msg.type === "done") {
            outcome = msg.outcome;
            setSimulation({
              outcome: msg.outcome,
              total_ticks: msg.total_ticks,
              world,
              agents,
              ticks: [...ticks],
            });
          }
        }
      }
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") {
        // User reset the simulation — not an error
        return;
      }
      const msg = err instanceof Error ? err.message : "Simulation failed";
      setError(msg);
      console.error("Simulation failed:", err);
    } finally {
      abortRef.current = null;
      setLoading(false);
      setLiveFollow(false);
    }
  }, []);

  // Auto-play interval (for post-simulation replay)
  useEffect(() => {
    if (playing && simulation && !loading) {
      intervalRef.current = window.setInterval(() => {
        setCurrentTick((prev) => {
          if (prev >= simulation.total_ticks) {
            setPlaying(false);
            return prev;
          }
          return prev + 1;
        });
      }, 1000 / speed);
    }
    return () => {
      if (intervalRef.current !== null) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
    };
  }, [playing, speed, simulation, loading]);

  const togglePlay = useCallback(() => {
    if (!simulation) return;
    if (loading) {
      // During streaming: toggle live follow
      setLiveFollow((l) => !l);
      return;
    }
    if (currentTick >= simulation.total_ticks) {
      setCurrentTick(1);
      setPlaying(true);
    } else {
      setPlaying((p) => !p);
    }
  }, [simulation, currentTick, loading]);

  const handleSetTick = useCallback((tick: number) => {
    setCurrentTick(tick);
    setPlaying(false);
    setLiveFollow(false);
  }, []);

  // Current tick data
  const tickData = simulation?.ticks[currentTick - 1] ?? null;

  const agentStates: AgentSnapshot[] = tickData
    ? tickData.agent_states
    : simulation
      ? simulation.agents.map((a) => ({
          name: a.name,
          hp: a.max_hp,
          max_hp: a.max_hp,
          mp: a.max_mp,
          max_mp: a.max_mp,
          room_id: "room_1",
          alive: true,
          weapon: a.weapon,
          armor: a.armor,
          ring: a.ring,
          last_action: "",
          last_result: "",
        }))
      : [];

  const roomStates = tickData?.room_states ?? {};
  // Show live events if we're following the stream and the current tick hasn't finalized yet
  const isOnLiveTick = loading && liveFollow && liveTick > 0 && !tickData;
  const events = isOnLiveTick ? liveEvents : (tickData?.events ?? []);
  const rooms = simulation?.world.rooms ?? worldRooms;

  return (
    <div className="h-screen flex flex-col overflow-hidden">
      <GameHeader
        outcome={loading ? null : simulation?.outcome ?? null}
        totalTicks={simulation?.total_ticks ?? 0}
        currentTick={currentTick}
        loading={loading}
        onRunSimulation={runSimulation}
        onResetSimulation={resetSimulation}
      />

      {error && (
        <div className="mx-2 sm:mx-4 mt-2 px-3 sm:px-4 py-2 sm:py-3 bg-red-900/50 border border-red-700 rounded-lg text-red-200 text-sm">
          {error}
        </div>
      )}

      {/* Main content: Map (top/left) | Event Log (bottom/right) */}
      <div className="flex-1 flex flex-col md:flex-row gap-2 sm:gap-4 p-2 sm:p-4 overflow-hidden min-h-0">
        <div className="w-full md:w-1/2 shrink-0 h-1/2 md:h-full min-h-0">
          <DungeonMap rooms={rooms} agentStates={agentStates} roomStates={roomStates} />
        </div>
        <div className="w-full md:w-1/2 h-1/2 md:h-full min-h-0">
          <EventLog events={events} currentTick={isOnLiveTick ? liveTick : currentTick} />
        </div>
      </div>

      {/* Tick controls */}
      <div className="px-2 sm:px-4 pb-2">
        <TickControls
          currentTick={currentTick}
          totalTicks={simulation?.total_ticks ?? 0}
          playing={loading ? liveFollow : playing}
          speed={speed}
          onSetTick={handleSetTick}
          onTogglePlay={togglePlay}
          onSetSpeed={setSpeed}
        />
      </div>

      {/* Agent panels (horizontal bottom row) */}
      <div className="px-2 sm:px-4 pb-2 sm:pb-4 overflow-x-auto">
        {agentStates.length > 0 && <AgentPanel agents={agentStates} rooms={rooms} />}
      </div>
    </div>
  );
}
