import { NextResponse } from "next/server";
import { DEMO_URL } from "@/lib/server-config";

export async function GET() {
  const res = await fetch(`${DEMO_URL}/scenarios`, { cache: "no-store" });
  const body = await res.text();
  return new NextResponse(body, { status: res.status, headers: { "content-type": "application/json" } });
}
