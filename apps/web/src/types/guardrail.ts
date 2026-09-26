// Domain types mirroring the agent API contracts and Supabase schema.
// Never redefine in component files — import from here.

export type ServiceName = "stable" | "canary" | "proxy" | `proxy->${string}`;

export type LogRow = {
  id: number;
  timestamp: string;
  service: ServiceName;
  endpoint: string;
  status_code: number;
  latency_ms: number;
  error_message: string | null;
  note: string | null;
  trace_id: string;
  target_id: string | null;
};

export type Verdict = "keep" | "escalate";

export type ProposalItem = {
  action: string;
  risk: number;
  blast_radius: string;
  reversibility: string;
  execute: { target: "stable" | "canary" } | null;
};

/** Persisted proposal set from /proposals list or /propose response */
export type ProposalSet = {
  id: number | null;
  verdict: string;
  reasons: string[];
  proposals: ProposalItem[];
  created_at?: string;
  target_id?: string | null;
};

/** POST /decide response */
export type DecideOut = {
  verdict: string;
  reasons: string[];
};

/** POST /execute response */
export type ExecuteOut = {
  ok: boolean;
  target: "stable" | "canary";
};

/** Audit trail row from Supabase */
export type AuditRow = {
  id: number;
  created_at: string;
  approver: string;
  action: string;
  outcome: string;
  proposal: {
    target: "stable" | "canary";
    proposal_id: number | null;
  } | null;
};

/** Proxy current route state */
export type ProxyRoute = {
  target: "stable" | "canary";
  ok?: boolean;
};

/** Approval body sent to /execute */
export type ApproveBody = {
  target: "stable" | "canary";
  approver: string;
  proposal_id: number;
  target_id?: string | null;
};

/** External target pair (BYO-API). can_flip is always false: advisory only. */
export type TargetPair = {
  id: string;
  owner_email: string;
  stable_url: string;
  canary_url: string;
  can_flip: boolean;
  created_at: string;
};

/** Generated probe case for a target. */
export type ProbeCase = {
  method: string;
  path: string;
  body: Record<string, unknown> | null;
  tier: string;
  source: "synth" | "llm";
};

/** POST /targets response */
export type TargetCreateResult = {
  target_id: string;
  endpoints: number;
  synth_cases: number;
  llm_cases: number;
};

/** POST /run response */
export type TrafficRunResult = {
  ok: boolean;
  rows: number;
  by_service: Record<string, number>;
  target_id: string | null;
};

export const VERDICT_LABELS: Record<string, string> = {
  keep: "Keep Canary",
  escalate: "Escalate",
};
