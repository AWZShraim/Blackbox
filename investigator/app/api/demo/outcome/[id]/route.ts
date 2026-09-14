import { NextResponse } from "next/server";
import { DEMO_URL } from "@/lib/server-config";

export async function GET(_request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const res = await fetch(`${DEMO_URL}/run/${id}/outcome`, { cache: "no-store" });
  const body = await res.text();
  return new NextResponse(body, { status: res.status, headers: { "content-type": "application/json" } });
}
