"use client";

import { useMemo } from "react";
import type { Session, Step } from "@/lib/types";
import { Timeline } from "./Timeline";
import { StepInspector } from "./StepInspector";

interface TraceExplorerProps {
  session: Session;
  steps: Step[];
  selectedStepId: string | null;
  onSelectStep: (stepId: string) => void;
}

/**
 * The Timeline + StepInspector split pane, as a controlled component —
 * selection state lives with the caller so DemoTour (Section 8's guided
 * tour) can drive it externally, while TraceView (the plain /sessions/[id]
 * viewer) just keeps it in local state. Same rendering either way (I9).
 */
export function TraceExplorer({ session, steps, selectedStepId, onSelectStep }: TraceExplorerProps) {
  const selectedStep = useMemo(
    () => steps.find((s) => s.step_id === selectedStepId) ?? null,
    [steps, selectedStepId],
  );

  return (
    <div className="flex min-h-0 flex-1">
      <div className="w-[380px] shrink-0 overflow-y-auto border-r border-gray-200 dark:border-white/10">
        <Timeline
          steps={steps}
          startedAt={session.started_at}
          selectedStepId={selectedStepId}
          onSelect={(step) => onSelectStep(step.step_id)}
        />
      </div>
      <div className="flex-1 overflow-y-auto p-6">
        {selectedStep ? (
          <StepInspector step={selectedStep} allSteps={steps} onJumpToStep={onSelectStep} />
        ) : (
          <p className="text-sm text-gray-500">Select a step to inspect it.</p>
        )}
      </div>
    </div>
  );
}
