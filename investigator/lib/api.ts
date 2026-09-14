// Client-safe API helpers. These call this app's own /api/* route handlers
// (same origin) rather than the recorder directly — the browser never
// needs network access to the recorder, only to this Next.js server. Server
// Components fetch the recorder directly instead; see
// lib/recorder-server.ts.
import type { Session } from "./types";

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
  }
}

async function get<T>(path: string): Promise<T> {
  const res = await fetch(path, { cache: "no-store" });
  if (!res.ok) {
    throw new ApiError(`${path} -> ${res.status}`, res.status);
  }
  return res.json() as Promise<T>;
}

export interface ListSessionsParams {
  human_id?: string;
  agent_id?: string;
  scenario_id?: string;
  limit?: number;
}

export function listSessions(params: ListSessionsParams = {}): Promise<Session[]> {
  const qs = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined) qs.set(key, String(value));
  }
  const suffix = qs.toString() ? `?${qs.toString()}` : "";
  return get<Session[]>(`/api/sessions${suffix}`);
}

export interface SearchResultStep {
  step_id: string;
  session_id: string;
  sequence: number;
  type: string;
  started_at: string;
}

export function searchByContentIdentifier(identifier: string, limit = 100): Promise<SearchResultStep[]> {
  const qs = new URLSearchParams({ identifier, limit: String(limit) });
  return get(`/api/search?${qs.toString()}`);
}
