import { NextResponse } from "next/server";
import { RECORDER_URL } from "@/lib/recorder-server";

export async function GET(_request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const res = await fetch(`${RECORDER_URL}/sessions/${id}`, { cache: "no-store" });
  const body = await res.text();
  return new NextResponse(body, { status: res.status, headers: { "content-type": "application/json" } });
}
