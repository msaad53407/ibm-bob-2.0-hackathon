/**
 * MTTD / MTTR query hook.
 *
 * Reads the three tables the metrics are derived from straight from Postgres
 * with the anon key — the same path use-logs.ts takes — rather than adding an
 * agent endpoint for a pure read. RLS already gates all three to admins, and
 * this keeps the arithmetic in one pure module (lib/mttd-mttr.ts) instead of
 * spread across a service and a view.
 *
 * `proposals` and `audit` go through the agent forwarders because those
 * endpoints already normalise the shapes; only `logs` is read directly, since
 * the agent exposes no log-listing route.
 */
"use client";

import { useQuery } from "@tanstack/react-query";
import { getSupabase } from "@/lib/supabase";
import { getProposals, getAudit } from "@/lib/api";
import {
  computeDetectionMetrics,
  type DetectionMetrics,
} from "@/lib/mttd-mttr";
import { queryKeys } from "./query-keys";
import type { LogRow, ProposalSet, AuditRow } from "@/types/guardrail";

/**
 * Canary-error rows fetched. The only limit this hook controls — the agent's
 * /proposals and /audit endpoints cap themselves at 10 and 20 rows
 * (list_proposals / list_audit), so a mean can draw on at most 10 escalations
 * and 20 executions. That is a small sample; the card shows the count so the
 * number is never read as more precise than it is.
 */
const LOG_LIMIT = 500;

async function fetchCanaryErrorLogs(
  targetId: string | null,
): Promise<LogRow[]> {
  let query = getSupabase()
    .from("logs")
    .select("timestamp, service, status_code")
    .eq("service", "canary")
    .gte("status_code", 500)
    .order("timestamp", { ascending: true })
    .limit(LOG_LIMIT);

  // Demo rows are target_id IS NULL; an external pair is scoped by id. Same
  // split every other query in the app uses — never "fetch everything".
  query = targetId ? query.eq("target_id", targetId) : query.is("target_id", null);

  const { data, error } = await query;
  if (error) throw error;
  return (data as LogRow[]) ?? [];
}

export function useDetectionMetrics(
  targetId: string | null = null,
): {
  data: DetectionMetrics | undefined;
  isLoading: boolean;
  error: string | null;
  refetch: () => void;
} {
  const query = useQuery({
    queryKey: queryKeys.detectionMetrics(targetId),
    queryFn: async (): Promise<DetectionMetrics> => {
      const [logs, proposals, audit] = await Promise.all([
        fetchCanaryErrorLogs(targetId),
        getProposals(),
        getAudit(),
      ]);

      // Scope to the same target before computing, so a demo escalation is
      // never paired with an external pair's probes.
      const scopedProposals = (proposals as ProposalSet[]).filter((p) =>
        targetId ? p.target_id === targetId : !p.target_id,
      );

      return computeDetectionMetrics(
        logs,
        scopedProposals,
        audit as AuditRow[],
      );
    },
    // Metrics are historical aggregates over a 1h attribution window; polling
    // faster than the slowest thing they measure is just noise.
    staleTime: 30_000,
  });

  return {
    data: query.data,
    isLoading: query.isLoading,
    error: query.error instanceof Error ? query.error.message : null,
    refetch: () => void query.refetch(),
  };
}
