"use client";

import { useState } from "react";
import type { Trace } from "@/lib/types";
import { useLiveTrace } from "@/lib/useLiveTrace";
import { TraceExplorer } from "./TraceExplorer";
import { SessionHeader } from "./SessionHeader";

interface TraceViewProps {
  trace: Trace;
}

/**
 * The plain session viewer (M6/M9) — SessionHeader + a live-updating
 * TraceExplorer with its own local selection state. /demo/[sessionId] uses
 * the same useLiveTrace + TraceExplorer building blocks directly instead,
 * so DemoTour can drive selection (I9: one rendering path either way).
 */
export function TraceView({ trace: initialTrace }: TraceViewProps) {
  const { session, steps } = useLiveTrace(initialTrace);
  const [selectedStepId, setSelectedStepId] = useState<string | null>(initialTrace.steps[0]?.step_id ?? null);

  return (
    <div className="flex h-full flex-col">
      <SessionHeader session={session} />
      <TraceExplorer session={session} steps={steps} selectedStepId={selectedStepId} onSelectStep={setSelectedStepId} />
    </div>
  );
}
