// Server-only URLs for the demo orchestrator and the mediator. Never
// imported by a "use client" file — same reasoning as RECORDER_URL in
// lib/recorder-server.ts: the browser only ever talks to this app's own
// /api/* routes.
export const DEMO_URL = process.env.DEMO_URL ?? "http://localhost:8020";
export const MEDIATOR_URL = process.env.MEDIATOR_URL ?? "http://localhost:8000";
