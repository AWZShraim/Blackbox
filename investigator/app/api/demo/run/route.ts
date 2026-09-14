import { NextResponse } from "next/server";
import { DEMO_URL } from "@/lib/server-config";

export async function POST(request: Request) {
  const body = await request.text();
  const res = await fetch(`${DEMO_URL}/run`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body,
  });
  const text = await res.text();
  return new NextResponse(text, { status: res.status, headers: { "content-type": "application/json" } });
}
