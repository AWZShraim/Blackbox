// Server-only: talks to the recorder directly. Used by app/api/* route
// handlers (proxying for client components) and by Server Components that
// fetch data for their own initial render. Never imported by a "use
// client" file — the browser never needs network access to the recorder,
// only to this Next.js server. Deliberately a plain (not NEXT_PUBLIC_) env
// var for that reason.
import type { Trace } from "./types";

export const RECORDER_URL = process.env.RECORDER_URL ?? "http://localhost:8010";

export class RecorderApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
  }
}

export async function getTraceServer(sessionId: string): Promise<Trace> {
  const res = await fetch(`${RECORDER_URL}/sessions/${sessionId}`, { cache: "no-store" });
  if (!res.ok) {
    throw new RecorderApiError(`GET /sessions/${sessionId} -> ${res.status}`, res.status);
  }
  return res.json() as Promise<Trace>;
}
