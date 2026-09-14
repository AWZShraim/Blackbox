"use client";

import clsx from "clsx";
import type { Step } from "@/lib/types";
import { STEP_TYPE_COLOR, STEP_TYPE_LABEL, formatRelativeMs, isFlagged, summarizeStep } from "@/lib/display";

interface TimelineProps {
  steps: Step[];
  startedAt: string;
  selectedStepId: string | null;
  onSelect: (step: Step) => void;
}

/**
 * Ordered, colour-coded view of every step (Section 6.5). Flagged steps
 * are visually distinct — not just a different colour, a left-edge marker
 * that survives at a glance even in a long trace. Works identically
 * whether `steps` is a full stored trace or a growing array during a live
 * run (I9) — this component has no opinion about where its data came from.
 */
export function Timeline({ steps, startedAt, selectedStepId, onSelect }: TimelineProps) {
  return (
    <ol className="flex flex-col">
      {steps.map((step) => {
        const color = STEP_TYPE_COLOR[step.type];
        const flagged = isFlagged(step);
        const selected = step.step_id === selectedStepId;
        return (
          <li key={step.step_id}>
            <button
              type="button"
              onClick={() => onSelect(step)}
              className={clsx(
                "group flex w-full items-start gap-3 border-l-2 px-3 py-2.5 text-left transition-colors",
                selected ? "border-l-gray-900 bg-gray-50 dark:border-l-white dark:bg-white/5" : "border-l-transparent hover:bg-gray-50 dark:hover:bg-white/5",
                flagged && "bg-red-50/60 dark:bg-red-950/20",
              )}
            >
              <span className={clsx("mt-1.5 h-2 w-2 shrink-0 rounded-full", color.bg)} aria-hidden />
              <span className="min-w-0 flex-1">
                <span className="flex items-baseline justify-between gap-2">
                  <span className={clsx("text-xs font-medium", color.text)}>{STEP_TYPE_LABEL[step.type]}</span>
                  <span className="shrink-0 font-mono text-[11px] text-gray-400">
                    {formatRelativeMs(startedAt, step.started_at)}
                  </span>
                </span>
                <span className="mt-0.5 block truncate text-sm text-gray-700 dark:text-gray-300">
                  {summarizeStep(step)}
                </span>
                {step.post_containment && (
                  <span className="mt-1 inline-block rounded bg-purple-100 px-1.5 py-0.5 text-[10px] font-medium text-purple-700 dark:bg-purple-900/40 dark:text-purple-300">
                    post-containment
                  </span>
                )}
                {flagged && (
                  <span className="ml-1 mt-1 inline-block rounded bg-red-100 px-1.5 py-0.5 text-[10px] font-medium text-red-700 dark:bg-red-900/40 dark:text-red-300">
                    flagged
                  </span>
                )}
              </span>
            </button>
          </li>
        );
      })}
    </ol>
  );
}
