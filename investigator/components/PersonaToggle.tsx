"use client";

import clsx from "clsx";
import type { Persona } from "@/lib/types";

interface PersonaToggleProps {
  persona: Persona;
  onChange: (persona: Persona) => void;
}

/**
 * Section 8: "guided flow with a persona toggle." Platform engineer sees
 * what was configured; responder sees the run itself.
 */
export function PersonaToggle({ persona, onChange }: PersonaToggleProps) {
  return (
    <div className="inline-flex rounded-full border border-gray-300 p-0.5 text-xs dark:border-white/20">
      {(["responder", "platform_engineer"] as const).map((p) => (
        <button
          key={p}
          type="button"
          onClick={() => onChange(p)}
          className={clsx(
            "rounded-full px-3 py-1 font-medium transition-colors",
            persona === p ? "bg-gray-900 text-white dark:bg-white dark:text-gray-900" : "text-gray-500",
          )}
        >
          {p === "responder" ? "Responder" : "Platform engineer"}
        </button>
      ))}
    </div>
  );
}
