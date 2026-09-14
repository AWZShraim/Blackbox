"use client";

import Link from "next/link";

export default function SessionError({ error }: { error: Error & { digest?: string } }) {
  return (
    <main className="flex h-screen flex-col items-center justify-center gap-3 text-center">
      <p className="text-lg font-medium">Could not load this session</p>
      <p className="max-w-md text-sm text-gray-500">
        The recorder may be unreachable. Check RECORDER_URL and that the recorder service is running.
      </p>
      <p className="max-w-md text-xs text-gray-400">{error.message}</p>
      <Link href="/" className="text-sm underline">
        Back to sessions
      </Link>
    </main>
  );
}
