"use client";

import { useEffect, useMemo, useState } from "react";
import type { Step } from "@/lib/types";
import { isContainmentEvent, isDetectionFlag, isPolicyDecision } from "@/lib/types";

interface DemoTourProps {
  steps: Step[];
  onSelectStep: (stepId: string) => void;
}

function pickTourSteps(steps: Step[]): Step[] {
  if (steps.length === 0) return [];
  const interesting = steps.filter(
    (s) => isDetectionFlag(s) || isContainmentEvent(s) || (isPolicyDecision(s) && s.payload.decision !== "allow"),
  );
  const picked = [steps[0], ...interesting, steps[steps.length - 1]];
  const seen = new Set<string>();
  return picked
    .filter((s) => (seen.has(s.step_id) ? false : (seen.add(s.step_id), true)))
    .sort((a, b) => a.sequence - b.sequence);
}

function narrate(step: Step): string {
  if (isDetectionFlag(step)) return `Blackbox flags this: ${step.payload.description}`;
  if (isContainmentEvent(step)) {
    return `Containment: ${step.payload.action.replace(/_/g, " ")}, initiated by ${step.payload.initiated_by}.`;
  }
  if (isPolicyDecision(step)) return `Policy ${step.payload.decision}s this call — ${step.payload.reason}`;
  if (step.type === "agent_lifecycle") return "The agent's task begins here.";
  return "The run continues.";
}

/**
 * Section 8's guided tour: next/back with one sentence of narration per
 * step. Picks the steps worth narrating algorithmically (flags,
 * containment, non-allow policy decisions, plus the bookends) rather than
 * hand-authored per-scenario scripts — the narration reads from the same
 * payload data the Responder view already shows, so it can never drift out
 * of sync with what actually happened in a given run.
 */
export function DemoTour({ steps, onSelectStep }: DemoTourProps) {
  const tourSteps = useMemo(() => pickTourSteps(steps), [steps]);
  const [index, setIndex] = useState(0);
  const clampedIndex = Math.min(index, Math.max(tourSteps.length - 1, 0));
  const current = tourSteps[clampedIndex];

  useEffect(() => {
    if (current) onSelectStep(current.step_id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [current?.step_id]);

  if (tourSteps.length === 0) {
    return <p className="border-t border-gray-200 px-4 py-2 text-xs text-gray-500 dark:border-white/10">Waiting for the run to produce steps…</p>;
  }

  return (
    <div className="flex items-center justify-between gap-3 border-t border-gray-200 bg-gray-50 px-4 py-2 text-xs dark:border-white/10 dark:bg-white/5">
      <p className="flex-1 text-gray-700 dark:text-gray-300">{narrate(current)}</p>
      <div className="flex shrink-0 items-center gap-2">
        <button
          type="button"
          disabled={clampedIndex === 0}
          onClick={() => setIndex((i) => Math.max(0, i - 1))}
          className="rounded border border-gray-300 px-2 py-1 disabled:opacity-40 dark:border-white/20"
        >
          Back
        </button>
        <span className="text-gray-400">
          {clampedIndex + 1} / {tourSteps.length}
        </span>
        <button
          type="button"
          disabled={clampedIndex >= tourSteps.length - 1}
          onClick={() => setIndex((i) => Math.min(tourSteps.length - 1, i + 1))}
          className="rounded border border-gray-300 px-2 py-1 disabled:opacity-40 dark:border-white/20"
        >
          Next
        </button>
      </div>
    </div>
  );
}
