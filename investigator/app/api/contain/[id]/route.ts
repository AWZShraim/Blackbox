import { NextResponse } from "next/server";

// Server-only. The browser never sees the operator key or the mediator's
// URL — same reasoning as lib/recorder-server.ts.
const MEDIATOR_URL = process.env.MEDIATOR_URL ?? "http://localhost:8000";
const OPERATOR_KEY = process.env.BLACKBOX_OPERATOR_KEY ?? "operator-dev-key-change-me";

export async function POST(request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const body = await request.text();
  const res = await fetch(`${MEDIATOR_URL}/sessions/${id}/contain`, {
    method: "POST",
    headers: { "content-type": "application/json", "X-Blackbox-Operator-Key": OPERATOR_KEY },
    body,
  });
  const text = await res.text();
  return new NextResponse(text, { status: res.status, headers: { "content-type": "application/json" } });
}
