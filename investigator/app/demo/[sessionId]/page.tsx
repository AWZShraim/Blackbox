import { notFound } from "next/navigation";
import { RecorderApiError, getTraceServer } from "@/lib/recorder-server";
import { DemoSessionView } from "@/components/DemoSessionView";
import type { Trace } from "@/lib/types";

async function loadTrace(id: string): Promise<Trace> {
  try {
    return await getTraceServer(id);
  } catch (err) {
    if (err instanceof RecorderApiError && err.status === 404) {
      notFound();
    }
    throw err;
  }
}

export default async function DemoSessionPage({
  params,
  searchParams,
}: {
  params: Promise<{ sessionId: string }>;
  searchParams: Promise<{ mode?: string; notice?: string }>;
}) {
  const { sessionId } = await params;
  const { mode, notice } = await searchParams;
  const trace = await loadTrace(sessionId);

  return (
    <main className="h-screen">
      <DemoSessionView trace={trace} mode={mode === "live" ? "live" : "recorded"} notice={notice ?? null} />
    </main>
  );
}
