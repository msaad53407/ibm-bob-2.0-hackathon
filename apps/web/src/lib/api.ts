/**
 * Agent API client. All calls go through these typed wrappers.
 * Browser calls same-origin /api/agent/* (Next Route Handler injects
 * ADMIN_TOKEN server-side); server code uses internal AGENT_URL directly.
 */
import type {
  AuditRow,
  ApproveBody,
  DecideOut,
  ExecuteOut,
  ProbeCase,
  ProposalSet,
  ProxyRoute,
  TargetCreateResult,
  TargetPair,
  TrafficRunResult,
} from "@/types/guardrail";

function agentBase(): string {
  // Server-side (Route Handlers / Server Actions) uses the internal Docker URL.
  // Browser uses the same-origin forwarder so ADMIN_TOKEN never leaves the server.
  if (typeof window === "undefined") {
    return process.env.AGENT_URL ?? "http://localhost:8003";
  }
  return "/api/agent";
}

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${agentBase()}${path}`, {
    headers: { "Content-Type": "application/json", ...init?.headers },
    ...init,
  });
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText);
    throw new Error(`Agent API ${path} → ${res.status}: ${text}`);
  }
  return res.json() as Promise<T>;
}

/** GET /health */
export function getHealth(): Promise<{ ok: boolean }> {
  return apiFetch("/health");
}

/** POST /decide — triggers Decision module, returns verdict + reasons */
export function postDecide(target_id?: string | null): Promise<DecideOut> {
  return apiFetch<DecideOut>("/decide", {
    method: "POST",
    body: JSON.stringify({ target_id: target_id ?? null }),
  });
}

/** POST /propose — Decision + Proposals + persist, returns ProposalSet */
export function postPropose(target_id?: string | null): Promise<ProposalSet> {
  return apiFetch<ProposalSet>("/propose", {
    method: "POST",
    body: JSON.stringify({ target_id: target_id ?? null }),
  });
}

/** GET /proposals — recent proposal sets, newest first */
export function getProposals(): Promise<ProposalSet[]> {
  return apiFetch<ProposalSet[]>("/proposals");
}

/** GET /audit — recent execution records */
export function getAudit(): Promise<AuditRow[]> {
  return apiFetch<AuditRow[]>("/audit");
}

/** POST /execute — approve + execute the traffic flip */
export function postExecute(body: ApproveBody): Promise<ExecuteOut> {
  return apiFetch<ExecuteOut>("/execute", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

/** POST /api/traffic/run — fire a probe batch (demo, or target_id for external) */
export function postTrafficRun(target_id?: string | null): Promise<TrafficRunResult> {
  // Traffic forwarder lives outside /api/agent/* (separate service).
  return fetch("/api/traffic/run", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ target_id: target_id ?? null }),
  }).then(async (res) => {
    if (!res.ok) {
      const text = await res.text().catch(() => res.statusText);
      throw new Error(`Traffic run → ${res.status}: ${text}`);
    }
    return res.json();
  });
}

// ── External targets (BYO-API): same-origin /api/runner/* forwarder ─────────

async function runnerFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api/runner${path}`, {
    headers: { "Content-Type": "application/json", ...init?.headers },
    ...init,
  });
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText);
    throw new Error(`Runner ${path} → ${res.status}: ${text}`);
  }
  return res.json() as Promise<T>;
}

/** GET /api/runner/targets — pairs owned by the signed-in admin */
export function listTargets(): Promise<TargetPair[]> {
  return runnerFetch<TargetPair[]>("/targets");
}

/** POST /api/runner/targets — connect URLs + OpenAPI spec, get cases back */
export function createTarget(body: {
  stable_url: string;
  canary_url: string;
  spec_text: string;
}): Promise<TargetCreateResult> {
  return runnerFetch<TargetCreateResult>("/targets", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

/** GET /api/runner/targets/{id}/cases — stored generated cases */
export function listTargetCases(target_id: string): Promise<ProbeCase[]> {
  return runnerFetch<ProbeCase[]>(`/targets/${target_id}/cases`);
}

/** GET proxy /admin/route — current routing target */
export function getProxyRoute(): Promise<ProxyRoute> {  // Server-side: use the internal Docker base URL directly (GET stays open).
  // Browser: same-origin forwarder (keeps working once proxy ports close).
  if (typeof window === "undefined") {
    const proxyBase = process.env.PROXY_BASE_URL ?? "http://proxy:8080";
    return fetch(`${proxyBase}/admin/route`).then((r) => r.json());
  }
  return fetch("/api/proxy/route").then((r) => r.json());
}
