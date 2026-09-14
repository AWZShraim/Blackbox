"use client";

import { useState } from "react";
import type { Session } from "@/lib/types";

interface ContainmentControlProps {
  session: Session;
}

/**
 * Stops forwarding and revokes credentials for the session (Section 6.5) —
 * the differentiating demo beat. After containment the timeline (fed by
 * useLiveTrace's SSE connection) keeps updating on its own, showing
 * whatever the agent tries next getting refused.
 *
 * Deliberately no window.prompt()/confirm() — native dialogs are blocked
 * in some embedding contexts (automated browsers, iframes) and are poor
 * UX besides; this is a small inline confirm panel instead.
 */
export function ContainmentControl({ session }: ContainmentControlProps) {
  const [open, setOpen] = useState(false);
  const [initiatedBy, setInitiatedBy] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [justContained, setJustContained] = useState(false);

  if (session.status === "contained" || session.status === "terminated" || justContained) {
    return (
      <span className="rounded bg-purple-100 px-3 py-1.5 text-sm font-medium text-purple-700 dark:bg-purple-900/40 dark:text-purple-300">
        {session.status === "terminated" ? "Terminated" : "Contained"}
      </span>
    );
  }

  if (session.status !== "running") {
    return null; // nothing to contain — the session already ended on its own
  }

  async function handleConfirm() {
    if (!initiatedBy.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`/api/contain/${session.session_id}`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ initiated_by: initiatedBy.trim(), reason: "manual containment from Investigator" }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || `contain failed: ${res.status}`);
      }
      setJustContained(true);
      setOpen(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : "contain failed");
    } finally {
      setLoading(false);
    }
  }

  if (open) {
    return (
      <div className="flex items-center gap-2 rounded border border-red-300 bg-red-50 px-3 py-2 dark:border-red-900 dark:bg-red-950/40">
        <label className="flex items-center gap-2 text-xs">
          <span className="text-red-700 dark:text-red-300">Your name/ID (I7):</span>
          <input
            autoFocus
            value={initiatedBy}
            onChange={(e) => setInitiatedBy(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleConfirm()}
            placeholder="responder"
            className="w-32 rounded border border-red-300 bg-white px-2 py-1 text-xs dark:border-red-800 dark:bg-black/30"
          />
        </label>
        <button
          type="button"
          onClick={handleConfirm}
          disabled={loading || !initiatedBy.trim()}
          className="rounded bg-red-600 px-2 py-1 text-xs font-semibold text-white hover:bg-red-700 disabled:opacity-50"
        >
          {loading ? "Containing…" : "Confirm contain"}
        </button>
        <button
          type="button"
          onClick={() => setOpen(false)}
          className="rounded border border-gray-300 px-2 py-1 text-xs dark:border-white/20"
        >
          Cancel
        </button>
        {error && <span className="text-xs text-red-600">{error}</span>}
      </div>
    );
  }

  return (
    <button
      type="button"
      onClick={() => setOpen(true)}
      className="rounded bg-red-600 px-3 py-1.5 text-sm font-semibold text-white hover:bg-red-700"
    >
      Contain session
    </button>
  );
}
