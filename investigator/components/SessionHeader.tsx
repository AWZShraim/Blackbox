import clsx from "clsx";
import type { Session } from "@/lib/types";
import { ContainmentControl } from "./ContainmentControl";

const STATUS_COLOR: Record<Session["status"], string> = {
  running: "bg-sky-100 text-sky-700 dark:bg-sky-900/40 dark:text-sky-300",
  completed: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300",
  failed: "bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300",
  contained: "bg-purple-100 text-purple-700 dark:bg-purple-900/40 dark:text-purple-300",
  terminated: "bg-gray-200 text-gray-700 dark:bg-white/10 dark:text-gray-300",
};

export function SessionHeader({ session }: { session: Session }) {
  return (
    <header className="flex flex-wrap items-center justify-between gap-3 border-b border-gray-200 px-6 py-4 dark:border-white/10">
      <div>
        <div className="flex items-center gap-2">
          <h1 className="text-sm font-semibold text-gray-900 dark:text-white">{session.task_description}</h1>
          <span className={clsx("rounded-full px-2 py-0.5 text-[11px] font-medium", STATUS_COLOR[session.status])}>
            {session.status}
          </span>
          {session.scenario_id && (
            <span className="rounded-full bg-gray-100 px-2 py-0.5 text-[11px] font-medium text-gray-600 dark:bg-white/10 dark:text-gray-300">
              {session.scenario_id}
            </span>
          )}
        </div>
        <p className="mt-1 font-mono text-xs text-gray-400">{session.session_id}</p>
      </div>
      <dl className="flex flex-wrap gap-x-6 gap-y-1 text-xs">
        <div>
          <dt className="text-gray-400">Agent</dt>
          <dd className="font-medium text-gray-800 dark:text-gray-200">
            {session.agent_id}@{session.agent_version}
          </dd>
        </div>
        <div>
          <dt className="text-gray-400">Human (I7)</dt>
          <dd className="font-medium text-gray-800 dark:text-gray-200">{session.human_id}</dd>
        </div>
        {session.human_context.role && (
          <div>
            <dt className="text-gray-400">Role</dt>
            <dd className="font-medium text-gray-800 dark:text-gray-200">{session.human_context.role}</dd>
          </div>
        )}
      </dl>
      <ContainmentControl session={session} />
    </header>
  );
}
