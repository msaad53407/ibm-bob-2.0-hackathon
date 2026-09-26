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
  getProxyRoute,
  postDecide,
  postPropose,
  postExecute,
  postTrafficRun,
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
      const data = await getProxyRoute();
      if (data.target !== "stable" && data.target !== "canary") {
        throw new Error("Proxy unreachable");
      }
      return data;
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

// ── Traffic run (probe batch) mutation ──────────────────────────────────────

export function useTrafficRun() {
  return useMutation({
    mutationFn: postTrafficRun,
    onSuccess: (data) => {
      toast.success(`Traffic run wrote ${data.rows} rows`, {
        description: "New logs stream in live — then Run Decision.",
      });
    },
    onError: (err) => {
      toast.error(`Traffic run failed: ${err.message}`);
    },
  });
}
