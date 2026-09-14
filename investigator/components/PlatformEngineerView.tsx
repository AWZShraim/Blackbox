"use client";

import { useEffect, useState } from "react";
import clsx from "clsx";
import type { Session, ToolCatalogueEntry } from "@/lib/types";

const RISK_COLOR: Record<string, string> = {
  low: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300",
  medium: "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300",
  high: "bg-orange-100 text-orange-700 dark:bg-orange-900/40 dark:text-orange-300",
  critical: "bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300",
};

interface PolicyRule {
  name: string;
  when: Record<string, unknown>;
  decision: string;
  fail_mode: string;
  reason: string;
}

/**
 * Section 8's platform-engineer persona: what was configured, not what
 * happened. Agent profile, the declared tool catalogue (I4 — no raw
 * execution tools, visibly), the loaded policy (the fourth seam — YAML,
 * not Python conditionals), credential scoping (I3), and the learned
 * baseline if one exists (Section 6.4 — none here is a legitimate,
 * expected answer, not an error).
 */
export function PlatformEngineerView({ session }: { session: Session }) {
  const [catalogue, setCatalogue] = useState<ToolCatalogueEntry[] | null>(null);
  const [policy, setPolicy] = useState<{ policy_id: string; raw: { rules: PolicyRule[] } } | null>(null);
  const [baseline, setBaseline] = useState<unknown>(undefined);

  useEffect(() => {
    fetch("/api/mediator/catalogue").then((r) => r.json()).then(setCatalogue).catch(() => setCatalogue([]));
    fetch("/api/mediator/policy").then((r) => r.json()).then(setPolicy).catch(() => setPolicy(null));
    fetch(`/api/mediator/baseline/agent/${encodeURIComponent(session.agent_id)}`)
      .then((r) => r.json())
      .then(setBaseline)
      .catch(() => setBaseline(null));
  }, [session.agent_id]);

  return (
    <div className="flex-1 overflow-y-auto p-6">
      <div className="mx-auto flex max-w-3xl flex-col gap-8">
        <section>
          <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-400">Agent profile</h2>
          <dl className="grid grid-cols-2 gap-3 text-sm">
            <div>
              <dt className="text-gray-400">Agent ID</dt>
              <dd className="font-medium">{session.agent_id}</dd>
            </div>
            <div>
              <dt className="text-gray-400">Version</dt>
              <dd className="font-medium">{session.agent_version}</dd>
            </div>
          </dl>
        </section>

        <section>
          <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-400">
            Declared tool catalogue (I4 — no raw execution tools)
          </h2>
          {catalogue === null ? (
            <p className="text-sm text-gray-500">Loading…</p>
          ) : (
            <ul className="flex flex-col divide-y divide-gray-200 dark:divide-white/10">
              {catalogue.map((t) => (
                <li key={t.name} className="flex items-center justify-between gap-3 py-2 text-sm">
                  <div>
                    <p className="font-mono font-medium">{t.name}</p>
                    <p className="text-xs text-gray-500">{t.description}</p>
                  </div>
                  <div className="flex shrink-0 items-center gap-2">
                    <span className="rounded bg-gray-100 px-1.5 py-0.5 text-[10px] font-medium dark:bg-white/10">
                      {t.tool_class}
                    </span>
                    <span className={clsx("rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase", RISK_COLOR[t.risk])}>
                      {t.risk}
                    </span>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section>
          <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-400">
            Policy (declarative YAML — the fourth seam, not Python conditionals)
          </h2>
          {policy === null ? (
            <p className="text-sm text-gray-500">Loading…</p>
          ) : (
            <ul className="flex flex-col gap-2">
              {policy.raw.rules.map((rule) => (
                <li key={rule.name} className="rounded border border-gray-200 p-2 text-xs dark:border-white/10">
                  <div className="flex items-center justify-between">
                    <span className="font-mono font-medium">{rule.name}</span>
                    <span
                      className={clsx(
                        "rounded px-1.5 py-0.5 font-semibold",
                        rule.decision === "allow"
                          ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300"
                          : "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300",
                      )}
                    >
                      {rule.decision}
                    </span>
                  </div>
                  <p className="mt-1 text-gray-500">{rule.reason}</p>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section>
          <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-400">
            Credential scoping (I3)
          </h2>
          <p className="text-sm text-gray-600 dark:text-gray-400">
            The agent never receives a database password, API key, or cloud token — only a session with the
            mediator. Every tool call mints a short-lived, single-use credential scoped to that one call
            (<code className="rounded bg-gray-100 px-1 dark:bg-white/10">credential_ref</code> in each tool_result
            step) and revokes it immediately after. See any tool_result step in the Responder view for a real
            credential_ref from this session.
          </p>
        </section>

        <section>
          <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-400">
            Learned baseline (Section 6.4)
          </h2>
          {baseline === undefined ? (
            <p className="text-sm text-gray-500">Loading…</p>
          ) : baseline ? (
            <pre className="overflow-x-auto rounded bg-gray-50 p-2 text-xs dark:bg-white/5">
              {JSON.stringify(baseline, null, 2)}
            </pre>
          ) : (
            <p className="text-sm text-gray-500">
              No baseline learned yet for <code className="font-mono">{session.agent_id}</code> — an observe-only
              learning pass hasn&apos;t been run. Baseline-dependent detectors (argument/sequence/volume anomaly)
              stay quiet until a platform engineer reviews and enables one; nothing here silently assumes anomalous.
            </p>
          )}
        </section>
      </div>
    </div>
  );
}
