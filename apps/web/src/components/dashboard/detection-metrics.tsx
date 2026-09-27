"use client";

import { StatCard } from "@/components/dashboard/stat-cards";
import { Button } from "@/components/ui/button";
import { RiRefreshLine } from "@remixicon/react";
import { useDetectionMetrics } from "@/hooks/use-detection-metrics";
import { formatDuration } from "@/lib/mttd-mttr";

/**
 * MTTD / MTTR tiles.
 *
 * Both numbers are defined narrowly on purpose, and the captions say so —
 * an unqualified "mean time to detect" invites the reader to assume
 * deploy-to-detect, which GuardRail cannot measure. It sees a failing probe,
 * not a bad deploy.
 */
export function DetectionMetricsCards() {
  const { data, isLoading, error, refetch } = useDetectionMetrics();

  if (error) {
    return (
      <StatCard
        title="Detection Latency"
        value="—"
        description={`Unavailable: ${error}`}
      />
    );
  }

  return (
    <>
      <StatCard
        title="MTTD"
        icon={
          <Button
            variant="ghost"
            size="icon-xs"
            onClick={refetch}
            disabled={isLoading}
            aria-label="Refresh detection metrics"
          >
            <RiRefreshLine className={isLoading ? "animate-spin" : ""} />
          </Button>
        }
        value={isLoading ? "—" : formatDuration(data?.mttdMs ?? null)}
        description={
          isLoading
            ? "Loading"
            : data?.mttdSamples
              ? `First failing probe → verdict${data.unattributed ? ` (${data.unattributed} escalation(s) had no failing probe in the 1h window)` : ""}`
              : "No escalation traced to a failing probe yet"
        }
      />
      <StatCard
        title="MTTR"
        value={isLoading ? "—" : formatDuration(data?.mttrMs ?? null)}
        description={
          isLoading
            ? "Loading"
            : data?.mttrSamples
              ? `Escalation → human approval (${data.mttrSamples} execution${data.mttrSamples === 1 ? "" : "s"})`
              : "No execution recorded yet"
        }
      />
    </>
  );
}
