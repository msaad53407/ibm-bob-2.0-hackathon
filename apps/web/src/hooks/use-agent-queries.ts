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
  listTargets,
  listTargetCases,
  createTarget,
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

export function useDecide(target_id?: string | null) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => postDecide(target_id),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: queryKeys.proposals });
    },
    onError: (err) => {
      toast.error(`Decision failed: ${err.message}`);
    },
  });
}

// ── Propose mutation ──────────────────────────────────────────────────────────

export function usePropose(target_id?: string | null) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => postPropose(target_id),
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

export function useTrafficRun(target_id?: string | null) {
  return useMutation({
    mutationFn: () => postTrafficRun(target_id),
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

// ── External targets (BYO-API) ──────────────────────────────────────────────

export function useTargets() {
  return useQuery({
    queryKey: queryKeys.targets,
    queryFn: listTargets,
  });
}

export function useTargetCases(target_id: string | null) {
  return useQuery({
    queryKey: queryKeys.targetCases(target_id ?? ""),
    queryFn: () => listTargetCases(target_id!),
    enabled: !!target_id,
  });
}

export function useCreateTarget() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: createTarget,
    onSuccess: (data) => {
      toast.success(
        `Target connected — ${data.endpoints} endpoints, ${data.synth_cases + data.llm_cases} cases`,
        { description: data.llm_cases > 0 ? "Includes LLM-generated edge cases." : "Deterministic cases (LLM unavailable)." },
      );
      void qc.invalidateQueries({ queryKey: queryKeys.targets });
    },
    onError: (err) => {
      toast.error(`Connect failed: ${err.message}`);
    },
  });
}
