import { NextResponse } from "next/server";
import { MEDIATOR_URL } from "@/lib/server-config";

export async function GET(
  _request: Request,
  { params }: { params: Promise<{ subjectType: string; subjectId: string }> },
) {
  const { subjectType, subjectId } = await params;
  const res = await fetch(`${MEDIATOR_URL}/baseline/${subjectType}/${encodeURIComponent(subjectId)}`, {
    cache: "no-store",
  });
  const body = await res.text();
  return new NextResponse(body, { status: res.status, headers: { "content-type": "application/json" } });
}
