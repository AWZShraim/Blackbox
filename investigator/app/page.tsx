import Link from "next/link";
import { ScenarioPicker } from "@/components/ScenarioPicker";

export default function LandingPage() {
  return (
    <main className="mx-auto flex max-w-3xl flex-col gap-8 p-8">
      <div>
        <h1 className="text-2xl font-semibold">Blackbox</h1>
        <p className="mt-3 text-sm leading-relaxed text-gray-600 dark:text-gray-400">
          Blackbox is EDR for AI agents: every model call and tool call an agent makes transits a mediator that
          records, verifies, and enforces policy against it. Pick a scenario below to watch a real (or recently
          captured) agent run — a flag fires, an action gets blocked, and you can trace the whole thing backward to
          exactly where it went wrong.
        </p>
      </div>

      <ScenarioPicker />

      <div className="flex items-center gap-4 border-t border-gray-200 pt-6 text-xs text-gray-500 dark:border-white/10">
        <Link href="/sessions" className="underline">
          Browse all sessions
        </Link>
        <Link href="/about" className="underline">
          About / scope
        </Link>
      </div>
    </main>
  );
}
