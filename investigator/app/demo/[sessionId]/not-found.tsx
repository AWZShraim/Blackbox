import Link from "next/link";

export default function DemoSessionNotFound() {
  return (
    <main className="flex h-screen flex-col items-center justify-center gap-3 text-center">
      <p className="text-lg font-medium">Session not found</p>
      <p className="max-w-md text-sm text-gray-500">
        This run may not have started yet, or the recorder hasn&apos;t caught up. Try again from the scenario picker.
      </p>
      <Link href="/" className="text-sm underline">
        Back to scenarios
      </Link>
    </main>
  );
}
