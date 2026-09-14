"use client";

import Link from "next/link";

export default function DemoSessionError({ error }: { error: Error & { digest?: string } }) {
  return (
    <main className="flex h-screen flex-col items-center justify-center gap-3 text-center">
      <p className="text-lg font-medium">Could not load this run</p>
      <p className="max-w-md text-sm text-gray-500">
        The recorder or demo service may be unreachable. Check RECORDER_URL / DEMO_URL.
      </p>
      <p className="max-w-md text-xs text-gray-400">{error.message}</p>
      <Link href="/" className="text-sm underline">
        Back to scenarios
      </Link>
    </main>
  );
}
