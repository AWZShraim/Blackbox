"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import type { Trace } from "@/lib/types";
import type { Persona } from "@/lib/types";
import { useLiveTrace } from "@/lib/useLiveTrace";
import { SessionHeader } from "./SessionHeader";
import { PersonaToggle } from "./PersonaToggle";
import { PlatformEngineerView } from "./PlatformEngineerView";
import { TraceExplorer } from "./TraceExplorer";
import { DemoTour } from "./DemoTour";

interface DemoSessionViewProps {
  trace: Trace;
  mode: "live" | "recorded";
  notice: string | null;
}

/**
 * The guided flow (Section 8): a persona toggle, and — for the responder
 * persona — a guided tour by default with a free-explore escape hatch.
 * Also owns the live-run outcome poll: if this was a live attempt that
 * didn't demonstrate anything, redirect to the fallback session with a
 * notice, rather than leaving the visitor staring at an uneventful run.
 */
export function DemoSessionView({ trace: initialTrace, mode, notice: initialNotice }: DemoSessionViewProps) {
  const router = useRouter();
  const { session, steps } = useLiveTrace(initialTrace);
  const [persona, setPersona] = useState<Persona>("responder");
  const [tourActive, setTourActive] = useState(true);
  const [selectedStepId, setSelectedStepId] = useState<string | null>(initialTrace.steps[0]?.step_id ?? null);
  const [notice, setNotice] = useState(initialNotice);

  useEffect(() => {
    if (mode !== "live") return;
    let cancelled = false;

    async function poll() {
      while (!cancelled) {
        try {
          const res = await fetch(`/api/demo/outcome/${initialTrace.session.session_id}`);
          const body = await res.json();
          if (cancelled) return;
          if (body.status === "fallback" && body.fallback_session_id) {
            const fallbackNotice = "showing a previous run — this live attempt did not demonstrate the scenario";
            router.replace(`/demo/${body.fallback_session_id}?mode=recorded&notice=${encodeURIComponent(fallbackNotice)}`);
            return;
          }
          if (body.status === "demonstrated") return;
        } catch {
          // transient — keep polling
        }
        await new Promise((r) => setTimeout(r, 1500));
      }
    }
    poll();
    return () => {
      cancelled = true;
    };
  }, [mode, initialTrace.session.session_id, router]);

  return (
    <div className="flex h-full flex-col">
      {notice && (
        <div className="flex items-center justify-between gap-3 bg-amber-100 px-4 py-2 text-xs text-amber-800 dark:bg-amber-900/40 dark:text-amber-200">
          <span>{notice}</span>
          <button type="button" onClick={() => setNotice(null)} className="shrink-0 font-semibold">
            dismiss
          </button>
        </div>
      )}
      <SessionHeader session={session} />
      <div className="flex items-center justify-between border-b border-gray-200 px-4 py-2 dark:border-white/10">
        <PersonaToggle persona={persona} onChange={setPersona} />
        {persona === "responder" && (
          <button type="button" onClick={() => setTourActive((v) => !v)} className="text-xs underline">
            {tourActive ? "Switch to free explore" : "Switch to guided tour"}
          </button>
        )}
      </div>

      {persona === "platform_engineer" ? (
        <PlatformEngineerView session={session} />
      ) : (
        <>
          <TraceExplorer session={session} steps={steps} selectedStepId={selectedStepId} onSelectStep={setSelectedStepId} />
          {tourActive && <DemoTour steps={steps} onSelectStep={setSelectedStepId} />}
        </>
      )}
    </div>
  );
}
