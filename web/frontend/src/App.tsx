import React, { useState, useEffect, useCallback, useRef } from "react";
import { SimulationResult, AgentSnapshot } from "./types";
import GameHeader from "./components/GameHeader";
import DungeonMap from "./components/DungeonMap";
import AgentPanel from "./components/AgentPanel";
import EventLog from "./components/EventLog";
import TickControls from "./components/TickControls";

export default function App() {
  const [simulation, setSimulation] = useState<SimulationResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [currentTick, setCurrentTick] = useState(1);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(1);
  const intervalRef = useRef<number | null>(null);

  const runSimulation = useCallback(async () => {
    setLoading(true);
    setPlaying(false);
    setSimulation(null);
    try {
      const res = await fetch("/api/simulate", { method: "POST" });
      const data: SimulationResult = await res.json();
      setSimulation(data);
      setCurrentTick(1);
    } catch (err) {
      console.error("Simulation failed:", err);
    } finally {
      setLoading(false);
    }
  }, []);

  // Auto-play interval
  useEffect(() => {
    if (playing && simulation) {
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
  }, [playing, speed, simulation]);

  const togglePlay = useCallback(() => {
    if (!simulation) return;
    if (currentTick >= simulation.total_ticks) {
      setCurrentTick(1);
      setPlaying(true);
    } else {
      setPlaying((p) => !p);
    }
  }, [simulation, currentTick]);

  const handleSetTick = useCallback((tick: number) => {
    setCurrentTick(tick);
    setPlaying(false);
  }, []);

  // Current tick data
  const tickData = simulation?.ticks[currentTick - 1] ?? null;

  // Agent states: from tick data, or initial states from simulation config
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
  const events = tickData?.events ?? [];
  const rooms = simulation?.world.rooms ?? [];

  return (
    <div className="h-screen flex flex-col">
      <GameHeader
        outcome={simulation?.outcome ?? null}
        totalTicks={simulation?.total_ticks ?? 0}
        currentTick={currentTick}
        loading={loading}
        onRunSimulation={runSimulation}
      />

      <div className="flex-1 flex gap-4 p-4 overflow-hidden">
        {/* Map */}
        <DungeonMap rooms={rooms} agentStates={agentStates} roomStates={roomStates} />
        {/* Agent panels */}
        {agentStates.length > 0 && <AgentPanel agents={agentStates} rooms={rooms} />}
      </div>

      {/* Bottom controls */}
      <div className="px-4 pb-2">
        <TickControls
          currentTick={currentTick}
          totalTicks={simulation?.total_ticks ?? 0}
          playing={playing}
          speed={speed}
          onSetTick={handleSetTick}
          onTogglePlay={togglePlay}
          onSetSpeed={setSpeed}
        />
      </div>

      {/* Event log */}
      <div className="px-4 pb-4">
        <EventLog events={events} currentTick={currentTick} />
      </div>
    </div>
  );
}
