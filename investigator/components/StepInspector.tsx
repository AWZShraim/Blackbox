"use client";

import clsx from "clsx";
import type { Step } from "@/lib/types";
import {
  isAgentLifecycle,
  isContainmentEvent,
  isDetectionFlag,
  isModelCall,
  isModelResponse,
  isPolicyDecision,
  isToolRequest,
  isToolResult,
} from "@/lib/types";
import { STEP_TYPE_COLOR, STEP_TYPE_LABEL, formatTimestamp } from "@/lib/display";
import { ContextInspector } from "./ContextInspector";

interface StepInspectorProps {
  step: Step;
  allSteps: Step[];
  onJumpToStep: (stepId: string) => void;
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-0.5">
      <dt className="text-[11px] font-medium uppercase tracking-wide text-gray-400">{label}</dt>
      <dd className="text-sm text-gray-800 dark:text-gray-200">{children}</dd>
    </div>
  );
}

function Mono({ children }: { children: React.ReactNode }) {
  return <code className="rounded bg-gray-100 px-1.5 py-0.5 font-mono text-xs dark:bg-white/10">{children}</code>;
}

/**
 * Step inspector (Section 6.5): full payload, timing, policy decision,
 * credential used, sandbox ID. For a tool_result, the relevant
 * policy_decision is its sibling under the same tool_request — resolved
 * here from `allSteps` via parent_step_id, not duplicated into the payload.
 */
export function StepInspector({ step, allSteps, onJumpToStep }: StepInspectorProps) {
  const color = STEP_TYPE_COLOR[step.type];
  const siblingPolicyDecision = isToolResult(step)
    ? allSteps.find((s) => isPolicyDecision(s) && s.parent_step_id === step.parent_step_id)
    : undefined;

  return (
    <div className="flex flex-col gap-5">
      <header className="flex items-center justify-between">
        <div>
          <span className={clsx("text-sm font-semibold", color.text)}>{STEP_TYPE_LABEL[step.type]}</span>
          <p className="text-xs text-gray-400">
            sequence {step.sequence} · {formatTimestamp(step.started_at)} · {step.duration_ms}ms
          </p>
        </div>
        {step.post_containment && (
          <span className="rounded bg-purple-100 px-2 py-1 text-[11px] font-medium text-purple-700 dark:bg-purple-900/40 dark:text-purple-300">
            recorded post-containment
          </span>
        )}
      </header>

      {isModelCall(step) && (
        <>
          <dl className="grid grid-cols-2 gap-3">
            <Field label="Model">{step.payload.model}</Field>
            <Field label="Tokens (prompt)">{step.payload.token_counts.prompt}</Field>
            <Field label="Tools offered">{step.payload.tools_offered.map((t) => t.name).join(", ") || "none"}</Field>
          </dl>
          <div>
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-400">
              Context window (provenance-tagged)
            </h3>
            <ContextInspector segments={step.payload.context_composition} />
          </div>
        </>
      )}

      {isModelResponse(step) && (
        <dl className="grid grid-cols-2 gap-3">
          <Field label="Stop reason">
            <Mono>{step.payload.stop_reason}</Mono>
          </Field>
          <Field label="Tokens (completion)">{step.payload.token_counts.completion}</Field>
          {step.payload.text && (
            <div className="col-span-2">
              <Field label="Text">
                <p className="whitespace-pre-wrap">{step.payload.text}</p>
              </Field>
            </div>
          )}
          {step.payload.tool_calls.length > 0 && (
            <div className="col-span-2">
              <Field label="Tool calls requested">
                <ul className="flex flex-col gap-1">
                  {step.payload.tool_calls.map((c) => (
                    <li key={c.tool_call_id}>
                      <Mono>
                        {c.tool_name}({JSON.stringify(c.arguments)})
                      </Mono>
                    </li>
                  ))}
                </ul>
              </Field>
            </div>
          )}
        </dl>
      )}

      {isToolRequest(step) && (
        <dl className="grid grid-cols-1 gap-3">
          <Field label="Tool">
            <Mono>{step.payload.tool_name}</Mono>
          </Field>
          <Field label="Arguments">
            <pre className="overflow-x-auto rounded bg-gray-50 p-2 text-xs dark:bg-white/5">
              {JSON.stringify(step.payload.arguments, null, 2)}
            </pre>
          </Field>
        </dl>
      )}

      {isToolResult(step) && (
        <dl className="grid grid-cols-2 gap-3">
          <Field label="Tool">
            <Mono>{step.payload.tool_name}</Mono>
          </Field>
          <Field label="Success">
            <span className={step.payload.success ? "text-emerald-600" : "text-red-600"}>
              {step.payload.success ? "yes" : "no"}
            </span>
          </Field>
          <Field label="Credential used">
            <Mono>{step.payload.credential_ref || "(none — denied before minting)"}</Mono>
          </Field>
          <Field label="Sandbox ID">
            <Mono>{step.payload.sandbox_id || "(none)"}</Mono>
          </Field>
          {siblingPolicyDecision && isPolicyDecision(siblingPolicyDecision) && (
            <div className="col-span-2">
              <Field label="Policy decision">
                <button
                  type="button"
                  onClick={() => onJumpToStep(siblingPolicyDecision.step_id)}
                  className="text-left underline decoration-dotted hover:text-gray-950 dark:hover:text-white"
                >
                  {siblingPolicyDecision.payload.decision} ({siblingPolicyDecision.payload.rule_matched}) —{" "}
                  {siblingPolicyDecision.payload.reason}
                </button>
              </Field>
            </div>
          )}
          {step.payload.error && (
            <div className="col-span-2">
              <Field label="Error">
                <p className="text-red-600">{step.payload.error}</p>
              </Field>
            </div>
          )}
          <div className="col-span-2">
            <Field label="Provenance attached to this result">
              <p>
                {step.payload.provenance.trust_level} · {step.payload.provenance.source_type}
                {step.payload.provenance.source_identifier ? ` · ${step.payload.provenance.source_identifier}` : ""}
              </p>
            </Field>
          </div>
          <div className="col-span-2">
            <Field label="Result">
              <pre className="overflow-x-auto rounded bg-gray-50 p-2 text-xs dark:bg-white/5">
                {JSON.stringify(step.payload.result, null, 2)}
              </pre>
            </Field>
          </div>
        </dl>
      )}

      {isPolicyDecision(step) && (
        <dl className="grid grid-cols-2 gap-3">
          <Field label="Decision">
            <span
              className={clsx(
                step.payload.decision === "allow" ? "text-emerald-600" : "text-amber-600",
                "font-medium",
              )}
            >
              {step.payload.decision}
            </span>
          </Field>
          <Field label="Fail mode">
            <Mono>{step.payload.fail_mode}</Mono>
          </Field>
          <Field label="Policy">
            <Mono>{step.payload.policy_id}</Mono>
          </Field>
          <Field label="Rule matched">
            <Mono>{step.payload.rule_matched}</Mono>
          </Field>
          <div className="col-span-2">
            <Field label="Reason">{step.payload.reason}</Field>
          </div>
        </dl>
      )}

      {isDetectionFlag(step) && (
        <dl className="grid grid-cols-2 gap-3">
          <Field label="Severity">
            <span className="font-medium text-red-600">{step.payload.severity}</span>
          </Field>
          <Field label="Detector">
            <Mono>{step.payload.detector_id}</Mono>
          </Field>
          <div className="col-span-2">
            <Field label="Description">{step.payload.description}</Field>
          </div>
          <div className="col-span-2">
            <Field label="Candidate triggers (ranked — not a single root cause)">
              <ol className="flex flex-col gap-1">
                {step.payload.candidate_triggers.map((t, i) => (
                  <li key={`${t.step_id}-${i}`}>
                    <button
                      type="button"
                      onClick={() => onJumpToStep(t.step_id)}
                      className="text-left underline decoration-dotted hover:text-gray-950 dark:hover:text-white"
                    >
                      #{i + 1} score {t.score.toFixed(2)} — {t.reasoning} [{t.signals.join(", ")}]
                    </button>
                  </li>
                ))}
              </ol>
            </Field>
          </div>
        </dl>
      )}

      {isContainmentEvent(step) && (
        <dl className="grid grid-cols-2 gap-3">
          <Field label="Action">
            <Mono>{step.payload.action}</Mono>
          </Field>
          <Field label="Initiated by">{step.payload.initiated_by}</Field>
        </dl>
      )}

      {isAgentLifecycle(step) && (
        <dl className="grid grid-cols-2 gap-3">
          <Field label="Event">
            <Mono>{step.payload.event}</Mono>
          </Field>
          {step.payload.initiated_by && <Field label="Initiated by">{step.payload.initiated_by}</Field>}
          {step.payload.reason && (
            <div className="col-span-2">
              <Field label="Reason">{step.payload.reason}</Field>
            </div>
          )}
        </dl>
      )}

      <details className="mt-2">
        <summary className="cursor-pointer text-xs text-gray-400 hover:text-gray-600">raw payload</summary>
        <pre className="mt-2 overflow-x-auto rounded bg-gray-50 p-2 text-xs dark:bg-white/5">
          {JSON.stringify(step.payload, null, 2)}
        </pre>
      </details>
    </div>
  );
}
