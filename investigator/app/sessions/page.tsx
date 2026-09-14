"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import clsx from "clsx";
import type { Session } from "@/lib/types";
import { listSessions, searchByContentIdentifier, type SearchResultStep } from "@/lib/api";

const STATUS_COLOR: Record<Session["status"], string> = {
  running: "bg-sky-100 text-sky-700",
  completed: "bg-emerald-100 text-emerald-700",
  failed: "bg-red-100 text-red-700",
  contained: "bg-purple-100 text-purple-700",
  terminated: "bg-gray-200 text-gray-700",
};

export default function SessionsPage() {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [humanFilter, setHumanFilter] = useState("");
  const [agentFilter, setAgentFilter] = useState("");
  const [contentQuery, setContentQuery] = useState("");
  const [contentResults, setContentResults] = useState<SearchResultStep[] | null>(null);

  async function refresh() {
    setLoading(true);
    setError(null);
    try {
      const results = await listSessions({
        human_id: humanFilter || undefined,
        agent_id: agentFilter || undefined,
        limit: 100,
      });
      setSessions(results);
    } catch {
      setError("Could not reach the investigator's API. Is the recorder running (RECORDER_URL)?");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- intentionally mount-only
  }, []);

  async function runContentSearch(e: React.FormEvent) {
    e.preventDefault();
    if (!contentQuery.trim()) {
      setContentResults(null);
      return;
    }
    const results = await searchByContentIdentifier(contentQuery.trim());
    setContentResults(results);
  }

  return (
    <main className="mx-auto flex max-w-5xl flex-col gap-8 p-8">
      <div>
        <Link href="/" className="text-xs underline">
          ← Back to scenarios
        </Link>
        <h1 className="mt-2 text-2xl font-semibold">All sessions</h1>
        <p className="mt-1 text-sm text-gray-500">
          Replay and analyse agent traces. Pick a session, or pivot from a content identifier (e.g. ticket:8814).
        </p>
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          refresh();
        }}
        className="flex flex-wrap items-end gap-3"
      >
        <label className="flex flex-col gap-1 text-xs text-gray-500">
          Human ID
          <input
            value={humanFilter}
            onChange={(e) => setHumanFilter(e.target.value)}
            placeholder="user:jane.doe"
            className="w-52 rounded border border-gray-300 px-2 py-1.5 text-sm dark:border-white/20 dark:bg-transparent"
          />
        </label>
        <label className="flex flex-col gap-1 text-xs text-gray-500">
          Agent ID
          <input
            value={agentFilter}
            onChange={(e) => setAgentFilter(e.target.value)}
            placeholder="support-agent"
            className="w-52 rounded border border-gray-300 px-2 py-1.5 text-sm dark:border-white/20 dark:bg-transparent"
          />
        </label>
        <button type="submit" className="rounded bg-gray-900 px-3 py-1.5 text-sm text-white dark:bg-white dark:text-gray-900">
          Filter
        </button>
      </form>

      <form onSubmit={runContentSearch} className="flex items-end gap-3 border-t border-gray-200 pt-6 dark:border-white/10">
        <label className="flex flex-1 flex-col gap-1 text-xs text-gray-500">
          Search by content identifier (tool name, ticket:id, doc:id, ...)
          <input
            value={contentQuery}
            onChange={(e) => setContentQuery(e.target.value)}
            placeholder="ticket:8814"
            className="rounded border border-gray-300 px-2 py-1.5 text-sm dark:border-white/20 dark:bg-transparent"
          />
        </label>
        <button type="submit" className="rounded border border-gray-300 px-3 py-1.5 text-sm dark:border-white/20">
          Search
        </button>
      </form>

      {contentResults && (
        <div className="rounded border border-gray-200 p-3 text-sm dark:border-white/10">
          {contentResults.length === 0 ? (
            <p className="text-gray-500">No steps reference {contentQuery}.</p>
          ) : (
            <ul className="flex flex-col gap-1">
              {contentResults.map((s) => (
                <li key={s.step_id}>
                  <Link href={`/sessions/${s.session_id}`} className="underline">
                    session {s.session_id.slice(0, 8)}
                  </Link>{" "}
                  · step #{s.sequence} ({s.type}) at {new Date(s.started_at).toLocaleString()}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      <div>
        {loading && <p className="text-sm text-gray-500">Loading sessions…</p>}
        {error && <p className="text-sm text-red-600">{error}</p>}
        {!loading && !error && sessions.length === 0 && (
          <p className="text-sm text-gray-500">No sessions yet. Run a scenario to produce one.</p>
        )}
        <ul className="flex flex-col divide-y divide-gray-200 dark:divide-white/10">
          {sessions.map((s) => (
            <li key={s.session_id}>
              <Link
                href={`/sessions/${s.session_id}`}
                className="flex items-center justify-between gap-4 py-3 hover:bg-gray-50 dark:hover:bg-white/5"
              >
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium">{s.task_description}</p>
                  <p className="text-xs text-gray-400">
                    {s.agent_id} · {s.human_id} · {new Date(s.started_at).toLocaleString()}
                  </p>
                </div>
                <span className={clsx("shrink-0 rounded-full px-2 py-0.5 text-[11px] font-medium", STATUS_COLOR[s.status])}>
                  {s.status}
                </span>
              </Link>
            </li>
          ))}
        </ul>
      </div>
    </main>
  );
}
