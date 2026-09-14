"use client";

import { useMemo, useState } from "react";
import type { Trace } from "@/lib/types";
import { Timeline } from "./Timeline";
import { StepInspector } from "./StepInspector";
import { SessionHeader } from "./SessionHeader";

interface TraceViewProps {
  trace: Trace;
}

/**
 * Composes Timeline + StepInspector against one `trace` value. Whether
 * that trace came from a single GET (replay/stored, M6) or is being
 * appended to live over a stream (M9/M10, I9) is entirely the caller's
 * concern — this component only ever renders "the steps it currently has."
 */
export function TraceView({ trace }: TraceViewProps) {
  const [selectedStepId, setSelectedStepId] = useState<string | null>(trace.steps[0]?.step_id ?? null);

  const selectedStep = useMemo(
    () => trace.steps.find((s) => s.step_id === selectedStepId) ?? null,
    [trace.steps, selectedStepId],
  );

  return (
    <div className="flex h-full flex-col">
      <SessionHeader session={trace.session} />
      <div className="flex min-h-0 flex-1">
        <div className="w-[380px] shrink-0 overflow-y-auto border-r border-gray-200 dark:border-white/10">
          <Timeline
            steps={trace.steps}
            startedAt={trace.session.started_at}
            selectedStepId={selectedStepId}
            onSelect={(step) => setSelectedStepId(step.step_id)}
          />
        </div>
        <div className="flex-1 overflow-y-auto p-6">
          {selectedStep ? (
            <StepInspector step={selectedStep} allSteps={trace.steps} onJumpToStep={setSelectedStepId} />
          ) : (
            <p className="text-sm text-gray-500">Select a step to inspect it.</p>
          )}
        </div>
      </div>
    </div>
  );
}
