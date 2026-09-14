import { notFound } from "next/navigation";
import { RecorderApiError, getTraceServer } from "@/lib/recorder-server";
import { TraceView } from "@/components/TraceView";
import type { Trace } from "@/lib/types";

async function loadTrace(id: string): Promise<Trace> {
  try {
    return await getTraceServer(id);
  } catch (err) {
    if (err instanceof RecorderApiError && err.status === 404) {
      notFound();
    }
    throw err; // caught by app/sessions/[id]/error.tsx
  }
}

export default async function SessionPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const trace = await loadTrace(id);
  return (
    <main className="h-screen">
      <TraceView trace={trace} />
    </main>
  );
}
