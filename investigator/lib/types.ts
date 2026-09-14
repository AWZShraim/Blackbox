// Mirrors common/schema.py exactly. That file is the source of truth
// (Section 5) — if these two drift, this file is wrong, not the other way
// around. Keep field names identical (the recorder returns Pydantic's
// `model_dump(mode="json")` shape verbatim, snake_case included).

export type SessionStatus = "running" | "completed" | "failed" | "contained" | "terminated";

export type StepType =
  | "model_call"
  | "model_response"
  | "tool_request"
  | "tool_result"
  | "policy_decision"
  | "detection_flag"
  | "containment_event"
  | "agent_lifecycle";

export type SourceType = "user_input" | "system_prompt" | "tool_result" | "agent_memory" | "sub_agent";
export type TrustLevel = "trusted" | "semi_trusted" | "untrusted";
export type PolicyDecisionValue = "allow" | "deny" | "require_approval";
export type FailMode = "fail_open" | "fail_closed";
export type Severity = "info" | "low" | "medium" | "high" | "critical";
export type ContainmentAction =
  | "forwarding_stopped"
  | "credentials_revoked"
  | "agent_terminated"
  | "released";
export type LifecycleEvent = "started" | "completed" | "failed" | "terminated" | "contained" | "released";

export interface HumanContext {
  role?: string | null;
  team?: string | null;
  auth_method?: string | null;
}

export interface TokenCounts {
  prompt: number;
  completion: number;
  total: number;
}

export interface ByteRange {
  start: number;
  end: number;
}

export interface ContainmentInfo {
  contained_at: string;
  initiated_by: string;
  actions: ContainmentAction[];
  reason?: string | null;
  released_at?: string | null;
}

export interface ProvenanceRecord {
  content_id: string;
  source_type: SourceType;
  source_step_id?: string | null;
  source_tool?: string | null;
  source_identifier?: string | null;
  trust_level: TrustLevel;
  entered_at: string;
  byte_range: ByteRange;
}

export interface ContextSegment {
  provenance: ProvenanceRecord;
  text: string;
}

export interface CandidateTrigger {
  step_id: string;
  content_id?: string | null;
  score: number;
  reasoning: string;
  signals: string[];
}

export interface Message {
  role: string;
  content: unknown;
}

export interface ToolSchema {
  name: string;
  description: string;
  input_schema: Record<string, unknown>;
}

export interface ModelCallPayload {
  model: string;
  messages: Message[];
  system_prompt?: string | null;
  tools_offered: ToolSchema[];
  token_counts: TokenCounts;
  context_composition: ContextSegment[];
}

export interface ToolCallRequest {
  tool_call_id: string;
  tool_name: string;
  arguments: Record<string, unknown>;
}

export interface ModelResponsePayload {
  stop_reason: string;
  text?: string | null;
  tool_calls: ToolCallRequest[];
  token_counts: TokenCounts;
}

export interface ToolRequestPayload {
  tool_name: string;
  arguments: Record<string, unknown>;
  requested_by: string;
}

export interface ToolResultPayload {
  tool_name: string;
  success: boolean;
  result: unknown;
  error?: string | null;
  credential_ref: string;
  sandbox_id: string;
  provenance: ProvenanceRecord;
}

export interface PolicyDecisionPayload {
  decision: PolicyDecisionValue;
  policy_id: string;
  rule_matched: string;
  reason: string;
  fail_mode: FailMode;
}

export interface DetectionFlagPayload {
  severity: Severity;
  detector_id: string;
  description: string;
  candidate_triggers: CandidateTrigger[];
  baseline_ref?: string | null;
}

export interface ContainmentEventPayload {
  action: ContainmentAction;
  initiated_by: string;
  post_containment: boolean;
}

export interface AgentLifecyclePayload {
  event: LifecycleEvent;
  reason?: string | null;
  initiated_by?: string | null;
}

export type StepPayload =
  | ModelCallPayload
  | ModelResponsePayload
  | ToolRequestPayload
  | ToolResultPayload
  | PolicyDecisionPayload
  | DetectionFlagPayload
  | ContainmentEventPayload
  | AgentLifecyclePayload;

export interface Step {
  step_id: string;
  session_id: string;
  sequence: number;
  type: StepType;
  started_at: string;
  duration_ms: number;
  parent_step_id?: string | null;
  payload: StepPayload;
  post_containment: boolean;
}

export interface Session {
  session_id: string;
  agent_id: string;
  agent_version: string;
  human_id: string;
  human_context: HumanContext;
  task_description: string;
  started_at: string;
  ended_at?: string | null;
  status: SessionStatus;
  containment?: ContainmentInfo | null;
  scenario_id?: string | null;
}

export interface Trace {
  session: Session;
  steps: Step[];
}

// -- narrowing helpers, since `payload`'s shape depends on `type` --------

export function isModelCall(step: Step): step is Step & { payload: ModelCallPayload } {
  return step.type === "model_call";
}
export function isModelResponse(step: Step): step is Step & { payload: ModelResponsePayload } {
  return step.type === "model_response";
}
export function isToolRequest(step: Step): step is Step & { payload: ToolRequestPayload } {
  return step.type === "tool_request";
}
export function isToolResult(step: Step): step is Step & { payload: ToolResultPayload } {
  return step.type === "tool_result";
}
export function isPolicyDecision(step: Step): step is Step & { payload: PolicyDecisionPayload } {
  return step.type === "policy_decision";
}
export function isDetectionFlag(step: Step): step is Step & { payload: DetectionFlagPayload } {
  return step.type === "detection_flag";
}
export function isContainmentEvent(step: Step): step is Step & { payload: ContainmentEventPayload } {
  return step.type === "containment_event";
}
export function isAgentLifecycle(step: Step): step is Step & { payload: AgentLifecyclePayload } {
  return step.type === "agent_lifecycle";
}

// -- demo mode (Section 8) --------------------------------------------

export interface ScenarioSummary {
  scenario_id: string;
  title: string;
  mechanism: string;
  is_live: boolean;
  notes: string;
}

export interface RunResponse {
  session_id: string;
  mode: "live" | "recorded";
  notice: string | null;
}

export interface OutcomeResponse {
  status: "pending" | "demonstrated" | "fallback";
  fallback_session_id: string | null;
}

export type Persona = "responder" | "platform_engineer";

export interface ToolCatalogueEntry {
  name: string;
  description: string;
  tool_class: "read" | "write";
  risk: "low" | "medium" | "high" | "critical";
  notes: string;
  input_schema: Record<string, unknown>;
}
