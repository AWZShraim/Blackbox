"use client";

import clsx from "clsx";
import type { ContextSegment } from "@/lib/types";
import { TRUST_LEVEL_COLOR } from "@/lib/display";

interface ContextInspectorProps {
  segments: ContextSegment[];
  /** content_id to scroll/highlight — set when arriving via backward tracing. */
  highlightContentId?: string | null;
  /** content_ids the injection heuristic fired on (wired up in M7). */
  injectionFlaggedContentIds?: Set<string>;
}

const TRUST_LABEL: Record<string, string> = {
  trusted: "Trusted",
  semi_trusted: "Semi-trusted",
  untrusted: "Untrusted",
};

/**
 * The differentiating view (Section 6.5): the full context window sent to
 * the model, with every segment tagged by where it came from and how much
 * it should be trusted. This is what makes "an injected ticket does not
 * stand out by formatting alone" (Section 7) into something a responder
 * can still catch — not by reading style, but by reading provenance.
 */
export function ContextInspector({
  segments,
  highlightContentId,
  injectionFlaggedContentIds,
}: ContextInspectorProps) {
  if (segments.length === 0) {
    return <p className="text-sm text-gray-500">No context composition recorded for this call.</p>;
  }

  return (
    <div className="flex flex-col gap-2">
      {segments.map((segment) => {
        const trust = TRUST_LEVEL_COLOR[segment.provenance.trust_level];
        const highlighted = highlightContentId === segment.provenance.content_id;
        const injectionFlagged = injectionFlaggedContentIds?.has(segment.provenance.content_id) ?? false;
        return (
          <div
            key={segment.provenance.content_id}
            id={`segment-${segment.provenance.content_id}`}
            className={clsx(
              "rounded-md border px-3 py-2 text-sm",
              trust.bg,
              trust.border,
              highlighted && "ring-2 ring-offset-1 ring-gray-900 dark:ring-white",
              injectionFlagged && "outline outline-2 outline-red-500",
            )}
          >
            <div className="mb-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px]">
              <span className={clsx("rounded-full px-2 py-0.5 font-semibold uppercase tracking-wide", trust.bg, trust.text)}>
                {TRUST_LABEL[segment.provenance.trust_level]}
              </span>
              <span className="text-gray-500">source: {segment.provenance.source_type}</span>
              {segment.provenance.source_tool && (
                <span className="text-gray-500">via {segment.provenance.source_tool}</span>
              )}
              {segment.provenance.source_identifier && (
                <span className="rounded bg-gray-100 px-1.5 py-0.5 font-mono text-gray-600 dark:bg-white/10 dark:text-gray-300">
                  {segment.provenance.source_identifier}
                </span>
              )}
              {injectionFlagged && (
                <span className="rounded bg-red-600 px-1.5 py-0.5 font-semibold text-white">
                  injection heuristic fired
                </span>
              )}
            </div>
            <p className="whitespace-pre-wrap break-words font-mono text-[13px] leading-snug text-gray-800 dark:text-gray-200">
              {segment.text}
            </p>
          </div>
        );
      })}
    </div>
  );
}
