/** Canonical values for the logs.service field. All writers must use these. */
export const ServiceName = {
  STABLE: "stable",
  CANARY: "canary",
  PROXY_EVENT: "proxy",
  PROXY_TRAFFIC: (target: "stable" | "canary") => `proxy->${target}` as const,
} as const;

export type ServiceNameValue = "stable" | "canary" | "proxy" | `proxy->${string}`;

export const ERROR_THRESHOLD = 500; // status_code >= this is an error
export const ERROR_MSG_MAX_LEN = 500;

export type LogRow = {
  timestamp: string;
  service: ServiceNameValue;
  endpoint: string;
  status_code: number;
  latency_ms: number;
  error_message: string | null;
  trace_id: string;
};

export type Verdict = "keep" | "escalate";

export type Proposal = {
  action: string; risk: number; blast_radius: string;
  reversibility: string; execute: { target: "stable" | "canary" } | null;
};
