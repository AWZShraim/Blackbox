import Link from "next/link";

export default function SessionNotFound() {
  return (
    <main className="flex h-screen flex-col items-center justify-center gap-3 text-center">
      <p className="text-lg font-medium">Session not found</p>
      <p className="max-w-md text-sm text-gray-500">No trace exists for this session id.</p>
      <Link href="/" className="text-sm underline">
        Back to sessions
      </Link>
    </main>
  );
}
