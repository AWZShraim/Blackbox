"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import clsx from "clsx";
import type { RunResponse, ScenarioSummary } from "@/lib/types";

const MECHANISM_LABEL: Record<string, string> = {
  reasoning_compromise: "Reasoning compromise",
  privilege_boundary_escape: "Privilege boundary escape",
  corrigibility_failure: "Corrigibility failure",
  excessive_agency: "Excessive agency",
};

/**
 * The landing page's scenario picker (Section 8): each card names the
 * mechanism and states whether it's live or recorded — never presented as
 * if a recorded one just ran. No free-text input anywhere on this page;
 * picking a card and pressing Run is the entire interaction surface.
 */
export function ScenarioPicker() {
  const router = useRouter();
  const [scenarios, setScenarios] = useState<ScenarioSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [runningId, setRunningId] = useState<string | null>(null);

  useEffect(() => {
    fetch("/api/demo/scenarios")
      .then((r) => r.json())
      .then(setScenarios)
      .catch(() => setError("Could not reach the demo service."))
      .finally(() => setLoading(false));
  }, []);

  async function runScenario(scenarioId: string) {
    setRunningId(scenarioId);
    setError(null);
    try {
      const res = await fetch("/api/demo/run", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ scenario_id: scenarioId }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || `run failed: ${res.status}`);
      }
      const body: RunResponse = await res.json();
      router.push(`/demo/${body.session_id}?mode=${body.mode}${body.notice ? `&notice=${encodeURIComponent(body.notice)}` : ""}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "run failed");
      setRunningId(null);
    }
  }

  if (loading) return <p className="text-sm text-gray-500">Loading scenarios…</p>;
  if (error) return <p className="text-sm text-red-600">{error}</p>;

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
      {scenarios.map((s) => (
        <div
          key={s.scenario_id}
          className="flex flex-col gap-3 rounded-lg border border-gray-200 p-4 dark:border-white/10"
        >
          <div className="flex items-start justify-between gap-2">
            <h3 className="text-sm font-semibold text-gray-900 dark:text-white">{s.title}</h3>
            <span
              className={clsx(
                "shrink-0 rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide",
                s.is_live
                  ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300"
                  : "bg-gray-200 text-gray-700 dark:bg-white/10 dark:text-gray-300",
              )}
            >
              {s.is_live ? "Live" : "Recorded"}
            </span>
          </div>
          <p className="text-xs font-medium text-gray-500">{MECHANISM_LABEL[s.mechanism] ?? s.mechanism}</p>
          <p className="text-xs leading-relaxed text-gray-600 dark:text-gray-400">{s.notes}</p>
          <button
            type="button"
            onClick={() => runScenario(s.scenario_id)}
            disabled={runningId !== null}
            className="mt-auto rounded bg-gray-900 px-3 py-1.5 text-xs font-semibold text-white hover:bg-gray-700 disabled:opacity-50 dark:bg-white dark:text-gray-900"
          >
            {runningId === s.scenario_id ? "Starting…" : "Run this scenario"}
          </button>
        </div>
      ))}
    </div>
  );
}
