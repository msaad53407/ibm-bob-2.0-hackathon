/**
 * Agent API query hooks.
 *
 * Reads  → useQuery  (cached, deduplicated, background-refreshable)
 * Writes → useMutation (optimistic-friendly, exposes isPending / error)
 */
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  getHealth,
  getProposals,
  getAudit,
  postDecide,
  postPropose,
  postExecute,
} from "@/lib/api";
import { queryKeys } from "./query-keys";
import type { ApproveBody } from "@/types/guardrail";

// ── Agent health ──────────────────────────────────────────────────────────────

export function useAgentHealth() {
  return useQuery({
    queryKey: queryKeys.health,
    queryFn: getHealth,
    refetchInterval: 15_000, // poll every 15s to surface outages quickly
  });
}

// ── Proxy route ───────────────────────────────────────────────────────────────

export function useProxyRoute() {
  return useQuery({
    queryKey: queryKeys.proxyRoute,
    queryFn: async () => {
      const proxyUrl =
        process.env.NEXT_PUBLIC_PROXY_URL ?? "http://localhost:8080";
      const res = await fetch(`${proxyUrl}/admin/route`);
      if (!res.ok) throw new Error("Proxy unreachable");
      return res.json() as Promise<{ target: "stable" | "canary" }>;
    },
    refetchInterval: 10_000,
  });
}

// ── Proposals (list) ──────────────────────────────────────────────────────────

export function useProposals() {
  return useQuery({
    queryKey: queryKeys.proposals,
    queryFn: getProposals,
  });
}

// ── Audit trail ───────────────────────────────────────────────────────────────

export function useAudit() {
  return useQuery({
    queryKey: queryKeys.audit,
    queryFn: getAudit,
  });
}

// ── Decide mutation ───────────────────────────────────────────────────────────

export function useDecide() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: postDecide,
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: queryKeys.proposals });
    },
    onError: (err) => {
      toast.error(`Decision failed: ${err.message}`);
    },
  });
}

// ── Propose mutation ──────────────────────────────────────────────────────────

export function usePropose() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: postPropose,
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: queryKeys.proposals });
    },
    onError: (err) => {
      toast.error(`Propose failed: ${err.message}`);
    },
  });
}

// ── Execute (traffic flip) mutation ───────────────────────────────────────────

export function useExecute() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: ApproveBody) => postExecute(body),
    onSuccess: (data) => {
      toast.success(
        `Traffic flipped to ${data.target}`,
        { description: "Execution recorded in Audit Trail." },
      );
      void qc.invalidateQueries({ queryKey: queryKeys.audit });
      void qc.invalidateQueries({ queryKey: queryKeys.proxyRoute });
      void qc.invalidateQueries({ queryKey: queryKeys.proposals });
    },
    onError: (err) => {
      toast.error(`Execution failed: ${err.message}`);
    },
  });
}
