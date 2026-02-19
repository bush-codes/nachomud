import React, { useState, useEffect, useCallback, useRef } from "react";
import { SimulationResult, AgentSnapshot, GameEventData, RoomInfo, RoomSnapshot, WorldInfo, ClassDefinition } from "./types";
import GameHeader from "./components/GameHeader";
import DungeonMap from "./components/DungeonMap";
import AgentPanel from "./components/AgentPanel";
import EventLog from "./components/EventLog";
import PartySelector from "./components/PartySelector";

export default function App() {
  const [simulation, setSimulation] = useState<SimulationResult | null>(null);
  const [worldRooms, setWorldRooms] = useState<RoomInfo[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [allEvents, setAllEvents] = useState<GameEventData[]>([]);
  const [latestAgentStates, setLatestAgentStates] = useState<AgentSnapshot[]>([]);
  const [latestRoomStates, setLatestRoomStates] = useState<Record<string, RoomSnapshot>>({});
  const [maxTicks, setMaxTicks] = useState(20);
  const [agentModel, setAgentModel] = useState("gemma3:4b");
  const [currentTick, setCurrentTick] = useState(0);
  const DEFAULT_WORLDS: WorldInfo[] = [
    { id: "shadowfell", name: "Shadowfell Rift", description: "" },
    { id: "frostpeak", name: "Frostpeak Citadel", description: "" },
    { id: "serpentmire", name: "The Serpent's Mire", description: "" },
    { id: "emberhollows", name: "The Ember Hollows", description: "" },
  ];
  const [worlds, setWorlds] = useState<WorldInfo[]>(DEFAULT_WORLDS);
  const [selectedWorld, setSelectedWorld] = useState("shadowfell");
  const [party, setParty] = useState<string[]>(["Warrior", "Mage", "Ranger"]);
  const [classDefinitions, setClassDefinitions] = useState<Record<string, ClassDefinition>>({});
  const abortRef = useRef<AbortController | null>(null);

  // Changing the world resets any completed/running simulation so the new map shows
  const handleWorldChange = useCallback((worldId: string) => {
    if (abortRef.current) {
      abortRef.current.abort();
      abortRef.current = null;
    }
    setSelectedWorld(worldId);
    setSimulation(null);
    setLoading(false);
    setAllEvents([]);
    setLatestAgentStates([]);
    setLatestRoomStates({});
    setCurrentTick(0);
  }, []);

  // Load available worlds and class definitions on mount
  useEffect(() => {
    fetch("/api/worlds")
      .then((res) => res.json())
      .then((data: WorldInfo[]) => setWorlds(data))
      .catch(() => {});
    fetch("/api/classes")
      .then((res) => res.json())
      .then((data: Record<string, ClassDefinition>) => setClassDefinitions(data))
      .catch(() => {});
  }, []);

  // Load world map when selection changes
  useEffect(() => {
    fetch(`/api/world?world_id=${encodeURIComponent(selectedWorld)}`)
      .then((res) => res.json())
      .then((data) => setWorldRooms(data.rooms ?? []))
      .catch(() => {});
  }, [selectedWorld]);

  const resetSimulation = useCallback(() => {
    if (abortRef.current) {
      abortRef.current.abort();
      abortRef.current = null;
    }
    setSimulation(null);
    setLoading(false);
    setError(null);
    setAllEvents([]);
    setLatestAgentStates([]);
    setLatestRoomStates({});
    setCurrentTick(0);
  }, []);

  const runSimulation = useCallback(async () => {
    // Abort any previous run
    if (abortRef.current) {
      abortRef.current.abort();
    }
    const controller = new AbortController();
    abortRef.current = controller;

    setLoading(true);
    setSimulation(null);
    setError(null);
    setAllEvents([{ agent: "system", action: "system", result: "Building world and summoning heroes...", room_id: "" }]);
    setLatestAgentStates([]);
    setLatestRoomStates({});
    setCurrentTick(0);

    try {
      const partyParam = party.length > 0 ? `&party=${encodeURIComponent(party.join(","))}` : "";
      const res = await fetch(`/api/simulate?max_ticks=${maxTicks}&agent_model=${encodeURIComponent(agentModel)}&world_id=${encodeURIComponent(selectedWorld)}${partyParam}`, { method: "POST", signal: controller.signal });
      if (!res.ok) {
        const body = await res.json().catch(() => null);
        throw new Error(body?.detail || `Server error: ${res.status}`);
      }

      const reader = res.body!.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      let world: { rooms: RoomInfo[] } = { rooms: [] };
      let agents: SimulationResult["agents"] = [];
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
            });
            const names = agents.map((a) => `${a.name} the ${a.agent_class}`).join(", ");
            setAllEvents((prev) => [...prev,
              { agent: "system", action: "system", result: `${names} enter the dungeon.`, room_id: "" },
            ]);
          } else if (msg.type === "event") {
            setAllEvents((prev) => [...prev, msg.event]);
            if (msg.tick !== undefined) {
              setCurrentTick(msg.tick);
            }
            if (msg.agent_states) {
              setLatestAgentStates(msg.agent_states);
            }
            if (msg.room_states) {
              setLatestRoomStates(msg.room_states);
            }
          } else if (msg.type === "tick") {
            setCurrentTick(msg.tick);
            // Belt and suspenders: also update states from tick messages
            if (msg.agent_states) {
              setLatestAgentStates(msg.agent_states);
            }
            if (msg.room_states) {
              setLatestRoomStates(msg.room_states);
            }
          } else if (msg.type === "done") {
            outcome = msg.outcome;
            setSimulation({
              outcome: msg.outcome,
              total_ticks: msg.total_ticks,
              world,
              agents,
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
    }
  }, [maxTicks, agentModel, selectedWorld, party]);

  // Derive agent states: use latest from stream, or fall back to initial agent info
  const agentStates: AgentSnapshot[] = latestAgentStates.length > 0
    ? latestAgentStates
    : simulation
      ? simulation.agents.map((a) => ({
          name: a.name,
          agent_class: a.agent_class,
          hp: a.max_hp,
          max_hp: a.max_hp,
          mp: a.max_mp,
          max_mp: a.max_mp,
          ap: 0,
          max_ap: 0,
          speed: 3,
          room_id: "room_1",
          alive: true,
          weapon: a.weapon,
          armor: a.armor,
          ring: a.ring,
          last_action: "",
          last_result: "",
          status_effects: [],
        }))
      : [];

  const rooms = simulation?.world.rooms ?? worldRooms;

  return (
    <div className="h-screen flex flex-col overflow-hidden">
      <GameHeader
        outcome={loading ? null : simulation?.outcome ?? null}
        loading={loading}
        currentTick={currentTick}
        maxTicks={maxTicks}
        agentModel={agentModel}
        worlds={worlds}
        selectedWorld={selectedWorld}
        onWorldChange={handleWorldChange}
        onMaxTicksChange={setMaxTicks}
        onAgentModelChange={setAgentModel}
        onRunSimulation={runSimulation}
        onResetSimulation={resetSimulation}
      />

      {!simulation && !loading && Object.keys(classDefinitions).length > 0 && (
        <PartySelector
          classDefinitions={classDefinitions}
          party={party}
          onPartyChange={setParty}
        />
      )}

      {error && (
        <div className="mx-2 sm:mx-4 mt-2 px-3 sm:px-4 py-2 sm:py-3 bg-red-900/50 border border-red-700 rounded-lg text-red-200 text-sm">
          {error}
        </div>
      )}

      {/* Main content: Map (top/left) | Event Log (bottom/right) */}
      <div className="flex-1 flex flex-col md:flex-row gap-2 sm:gap-4 p-2 sm:p-4 overflow-hidden min-h-0">
        <div className="w-full md:w-1/2 shrink-0 h-1/2 md:h-full min-h-0">
          <DungeonMap rooms={rooms} agentStates={agentStates} roomStates={latestRoomStates} />
        </div>
        <div className="w-full md:w-1/2 h-1/2 md:h-full min-h-0">
          <EventLog events={allEvents} />
        </div>
      </div>

      {/* Agent panels (horizontal bottom row) */}
      <div className="px-2 sm:px-4 pb-2 sm:pb-4 overflow-x-auto">
        {agentStates.length > 0 && <AgentPanel agents={agentStates} rooms={rooms} />}
      </div>
    </div>
  );
}
