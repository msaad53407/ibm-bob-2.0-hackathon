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
  ProposalSet,
  ProxyRoute,
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
export function postDecide(): Promise<DecideOut> {
  return apiFetch<DecideOut>("/decide", { method: "POST" });
}

/** POST /propose — Decision + Proposals + persist, returns ProposalSet */
export function postPropose(): Promise<ProposalSet> {
  return apiFetch<ProposalSet>("/propose", { method: "POST" });
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

/** GET proxy /admin/route — current routing target */
export function getProxyRoute(): Promise<ProxyRoute> {
  // Server-side: use the internal Docker base URL directly (GET stays open).
  // Browser: same-origin forwarder (keeps working once proxy ports close).
  if (typeof window === "undefined") {
    const proxyBase = process.env.PROXY_BASE_URL ?? "http://proxy:8080";
    return fetch(`${proxyBase}/admin/route`).then((r) => r.json());
  }
  return fetch("/api/proxy/route").then((r) => r.json());
}
