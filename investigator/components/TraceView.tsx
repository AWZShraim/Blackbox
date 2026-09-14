"use client";

import { useMemo, useState } from "react";
import type { Trace } from "@/lib/types";
import { useLiveTrace } from "@/lib/useLiveTrace";
import { Timeline } from "./Timeline";
import { StepInspector } from "./StepInspector";
import { SessionHeader } from "./SessionHeader";

interface TraceViewProps {
  trace: Trace;
}

/**
 * Composes Timeline + StepInspector against one live-updating trace (I9:
 * one rendering path for both live and recorded). `trace` is only the
 * server-rendered first paint — useLiveTrace immediately opens the same
 * SSE channel a purely-live viewer would use, so a session already
 * complete when this page loads and one still running behave identically
 * from here on: both just render "the steps received so far."
 */
export function TraceView({ trace: initialTrace }: TraceViewProps) {
  const { session, steps } = useLiveTrace(initialTrace);
  const [selectedStepId, setSelectedStepId] = useState<string | null>(initialTrace.steps[0]?.step_id ?? null);

  const selectedStep = useMemo(
    () => steps.find((s) => s.step_id === selectedStepId) ?? null,
    [steps, selectedStepId],
  );

  return (
    <div className="flex h-full flex-col">
      <SessionHeader session={session} />
      <div className="flex min-h-0 flex-1">
        <div className="w-[380px] shrink-0 overflow-y-auto border-r border-gray-200 dark:border-white/10">
          <Timeline
            steps={steps}
            startedAt={session.started_at}
            selectedStepId={selectedStepId}
            onSelect={(step) => setSelectedStepId(step.step_id)}
          />
        </div>
        <div className="flex-1 overflow-y-auto p-6">
          {selectedStep ? (
            <StepInspector step={selectedStep} allSteps={steps} onJumpToStep={setSelectedStepId} />
          ) : (
            <p className="text-sm text-gray-500">Select a step to inspect it.</p>
          )}
        </div>
      </div>
    </div>
  );
}
