import type { Step, StepType, TrustLevel } from "./types";
import {
  isAgentLifecycle,
  isContainmentEvent,
  isDetectionFlag,
  isModelCall,
  isModelResponse,
  isPolicyDecision,
  isToolRequest,
  isToolResult,
} from "./types";

export const STEP_TYPE_LABEL: Record<StepType, string> = {
  model_call: "Model call",
  model_response: "Model response",
  tool_request: "Tool request",
  tool_result: "Tool result",
  policy_decision: "Policy decision",
  detection_flag: "Detection flag",
  containment_event: "Containment",
  agent_lifecycle: "Lifecycle",
};

// Tailwind class groups per step type — timeline dots, chips, borders.
// Kept centralized so the same step always reads the same way everywhere.
export const STEP_TYPE_COLOR: Record<StepType, { bg: string; text: string; ring: string }> = {
  model_call: { bg: "bg-sky-500", text: "text-sky-700", ring: "ring-sky-200" },
  model_response: { bg: "bg-indigo-500", text: "text-indigo-700", ring: "ring-indigo-200" },
  tool_request: { bg: "bg-slate-400", text: "text-slate-700", ring: "ring-slate-200" },
  tool_result: { bg: "bg-teal-500", text: "text-teal-700", ring: "ring-teal-200" },
  policy_decision: { bg: "bg-amber-500", text: "text-amber-700", ring: "ring-amber-200" },
  detection_flag: { bg: "bg-red-600", text: "text-red-700", ring: "ring-red-200" },
  containment_event: { bg: "bg-purple-600", text: "text-purple-700", ring: "ring-purple-200" },
  agent_lifecycle: { bg: "bg-gray-400", text: "text-gray-600", ring: "ring-gray-200" },
};

export const TRUST_LEVEL_COLOR: Record<TrustLevel, { bg: string; text: string; border: string }> = {
  trusted: { bg: "bg-emerald-50", text: "text-emerald-700", border: "border-emerald-300" },
  semi_trusted: { bg: "bg-amber-50", text: "text-amber-700", border: "border-amber-300" },
  untrusted: { bg: "bg-red-50", text: "text-red-700", border: "border-red-300" },
};

export function isFlagged(step: Step): boolean {
  if (isDetectionFlag(step)) return true;
  if (isPolicyDecision(step)) return step.payload.decision !== "allow";
  if (isToolResult(step)) return step.payload.success === false;
  return false;
}

/** One-line summary for the timeline row — the thing a responder scans. */
export function summarizeStep(step: Step): string {
  if (isModelCall(step)) return `${step.payload.model} · ${step.payload.messages.length} messages`;
  if (isModelResponse(step)) {
    const toolNames = step.payload.tool_calls.map((c) => c.tool_name).join(", ");
    return toolNames ? `requests ${toolNames}` : (step.payload.text?.slice(0, 80) ?? step.payload.stop_reason);
  }
  if (isToolRequest(step)) return `${step.payload.tool_name}(${JSON.stringify(step.payload.arguments)})`;
  if (isToolResult(step)) {
    return step.payload.success
      ? `${step.payload.tool_name} succeeded`
      : `${step.payload.tool_name} failed: ${step.payload.error ?? "unknown error"}`;
  }
  if (isPolicyDecision(step)) return `${step.payload.decision} — ${step.payload.reason}`;
  if (isDetectionFlag(step)) return `[${step.payload.severity}] ${step.payload.detector_id}: ${step.payload.description}`;
  if (isContainmentEvent(step)) return `${step.payload.action} by ${step.payload.initiated_by}`;
  if (isAgentLifecycle(step)) return `${step.payload.event}${step.payload.reason ? ` — ${step.payload.reason}` : ""}`;
  return "";
}

export function formatTimestamp(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleTimeString(undefined, { hour12: false, hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

export function formatRelativeMs(startIso: string, iso: string): string {
  const deltaMs = new Date(iso).getTime() - new Date(startIso).getTime();
  return `+${(deltaMs / 1000).toFixed(2)}s`;
}
