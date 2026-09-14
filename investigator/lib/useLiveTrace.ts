"use client";

import { useEffect, useRef, useState } from "react";
import type { Session, Step, Trace } from "./types";

/**
 * I9: live and recorded traces render identically — this hook is the one
 * place that matters for that. It always opens the same SSE connection
 * regardless of the session's status; a completed session's stream just
 * replays everything once and closes, a running one keeps tailing. The
 * Timeline/StepInspector/ContextInspector components never know which
 * happened, they only ever see `steps` grow.
 */
export function useLiveTrace(initial: Trace) {
  const [session, setSession] = useState<Session>(initial.session);
  const [steps, setSteps] = useState<Step[]>(initial.steps);
  const seenStepIds = useRef<Set<string>>(new Set(initial.steps.map((s) => s.step_id)));

  useEffect(() => {
    const source = new EventSource(`/api/sessions/${initial.session.session_id}/stream`);

    source.addEventListener("session", (e) => {
      const updated = JSON.parse((e as MessageEvent).data) as Session;
      setSession(updated);
    });

    source.addEventListener("step", (e) => {
      const step = JSON.parse((e as MessageEvent).data) as Step;
      if (seenStepIds.current.has(step.step_id)) return;
      seenStepIds.current.add(step.step_id);
      setSteps((prev) => [...prev, step].sort((a, b) => a.sequence - b.sequence));
    });

    // EventSource retries on its own; a session that has ended just stops
    // sending and the retries quietly no-op against a closed stream.
    return () => source.close();
  }, [initial.session.session_id]);

  return { session, steps };
}
