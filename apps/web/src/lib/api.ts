/**
 * Agent API client. All calls go through these typed wrappers.
 * Base URL is read from NEXT_PUBLIC_AGENT_URL (client-side) or
 * AGENT_URL (server actions), falling back to localhost:8003.
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
  // Server-side (Route Handlers / Server Actions) uses the internal Docker URL
  if (typeof window === "undefined") {
    return process.env.AGENT_URL ?? "http://localhost:8003";
  }
  return process.env.NEXT_PUBLIC_AGENT_URL ?? "http://localhost:8003";
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
  const proxyBase =
    typeof window === "undefined"
      ? (process.env.PROXY_ADMIN_URL ?? "http://proxy:8080")
      : (process.env.NEXT_PUBLIC_PROXY_URL ?? "http://localhost:8080");
  return fetch(`${proxyBase}/admin/route`).then((r) => r.json());
}
