import React from "react";
import { ClassDefinition, CLASS_COLORS } from "../types";

interface PartySelectorProps {
  classDefinitions: Record<string, ClassDefinition>;
  party: string[];
  onPartyChange: (party: string[]) => void;
}

const ABILITY_DISPLAY: Record<string, string> = {
  attack: "Attack",
  cleave: "Cleave",
  taunt: "Taunt",
  defend: "Defend",
  rally: "Rally",
  smite: "Smite",
  lay_on_hands: "Lay on Hands",
  shield: "Shield",
  consecrate: "Consecrate",
  missile: "Missile",
  arcane_storm: "Arcane Storm",
  curse: "Curse",
  barrier: "Barrier",
  heal: "Heal",
  ward: "Ward",
  holy_bolt: "Holy Bolt",
  cure: "Cure",
  aimed_shot: "Aimed Shot",
  volley: "Volley",
  poison_arrow: "Poison Arrow",
  sleep: "Sleep",
  backstab: "Backstab",
  bleed: "Bleed",
  evade: "Evade",
  smoke_bomb: "Smoke Bomb",
};

export default function PartySelector({ classDefinitions, party, onPartyChange }: PartySelectorProps) {
  const toggleClass = (className: string) => {
    if (party.includes(className)) {
      onPartyChange(party.filter((c) => c !== className));
    } else if (party.length < 3) {
      onPartyChange([...party, className]);
    }
  };

  return (
    <div className="mx-2 sm:mx-4 mt-2">
      <div className="text-xs text-gray-400 mb-2">
        Select your party (max 3):
        <span className="ml-2 text-gray-500">{party.length}/3</span>
      </div>
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2">
        {Object.entries(classDefinitions).map(([className, cls]) => {
          const selected = party.includes(className);
          const colors = CLASS_COLORS[className] || CLASS_COLORS.Warrior;
          const disabled = !selected && party.length >= 3;

          return (
            <button
              key={className}
              onClick={() => toggleClass(className)}
              disabled={disabled}
              className={`
                p-2 rounded-lg border text-left transition-all text-xs
                ${selected
                  ? `${colors.bg} ${colors.border} ${colors.text} ring-1 ring-opacity-50`
                  : disabled
                    ? "bg-gray-900/30 border-gray-800 text-gray-600 cursor-not-allowed opacity-50"
                    : "bg-gray-900/30 border-gray-700 text-gray-400 hover:border-gray-500"
                }
              `}
            >
              <div className="font-bold text-sm" style={selected ? { color: colors.primary } : {}}>
                {className}
              </div>
              <div className="text-[10px] text-gray-500 mt-0.5">
                {cls.default_name} &middot; HP:{cls.hp} &middot;
                {cls.resource_type === "ap" ? ` AP:${cls.resource_max}` : ` MP:${cls.resource_max}`}
                {" "}&middot; SPD:{cls.speed}
              </div>
              <div className="text-[10px] text-gray-600 mt-1 leading-tight">
                {cls.abilities.filter(a => a !== "attack").map(a => ABILITY_DISPLAY[a] || a).join(", ")}
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}
