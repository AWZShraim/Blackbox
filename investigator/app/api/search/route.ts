import { NextRequest, NextResponse } from "next/server";
import { RECORDER_URL } from "@/lib/recorder-server";

export async function GET(request: NextRequest) {
  const qs = request.nextUrl.search;
  const res = await fetch(`${RECORDER_URL}/search${qs}`, { cache: "no-store" });
  const body = await res.text();
  return new NextResponse(body, { status: res.status, headers: { "content-type": "application/json" } });
}
