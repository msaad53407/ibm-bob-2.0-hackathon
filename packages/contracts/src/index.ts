export type LogRow = {
  timestamp: string; service: string; endpoint: string;
  status_code: number; latency_ms: number;
  error_message: string | null; trace_id: string;
};
export type Verdict = "keep" | "escalate";
export type Proposal = {
  action: string; risk: number; blast_radius: string;
  reversibility: string; execute: { target: "stable" | "canary" } | null;
};
