"use client";

import {
  RiCheckLine,
  RiCloseLine,
  RiRefreshLine,
  RiTimeLine,
  RiShieldCheckLine,
} from "@remixicon/react";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Separator } from "@/components/ui/separator";
import { useAudit } from "@/hooks/use-agent-queries";
import type { AuditRow } from "@/types/guardrail";

// ── Outcome indicator ─────────────────────────────────────────────────────────

function OutcomeIcon({ outcome }: { outcome: string }) {
  const ok = outcome.includes("200");
  return ok ? (
    <div className="flex size-8 shrink-0 items-center justify-center rounded-full border border-emerald-500/30 bg-emerald-500/10">
      <RiCheckLine className="size-4 text-emerald-600 dark:text-emerald-400" />
    </div>
  ) : (
    <div className="flex size-8 shrink-0 items-center justify-center rounded-full border border-red-500/30 bg-red-500/10">
      <RiCloseLine className="size-4 text-red-600 dark:text-red-400" />
    </div>
  );
}

// ── Single timeline entry ─────────────────────────────────────────────────────

function AuditEntry({
  row,
  isLast,
}: {
  row: AuditRow;
  isLast: boolean;
}) {
  const target = row.proposal?.target;
  const ok = row.outcome.includes("200");

  return (
    <div className="relative flex gap-4">
      {/* Vertical connector line */}
      {!isLast && (
        <div className="absolute left-4 top-8 bottom-0 w-px bg-border" />
      )}

      <OutcomeIcon outcome={row.outcome} />

      <div className="flex-1 pb-6 min-w-0">
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="text-sm font-medium leading-snug">{row.action}</p>
            <div className="mt-1.5 flex flex-wrap gap-2 text-[10px] text-muted-foreground">
              <span className="flex items-center gap-1">
                <RiShieldCheckLine className="size-3" />
                Approver: <strong className="text-foreground">{row.approver}</strong>
              </span>
              {target && (
                <Badge
                  variant="outline"
                  className={
                    target === "canary"
                      ? "border-violet-500/20 bg-violet-500/10 text-[10px] text-violet-600 dark:text-violet-400"
                      : "border-blue-500/20 bg-blue-500/10 text-[10px] text-blue-600 dark:text-blue-400"
                  }
                >
                  → {target}
                </Badge>
              )}
              <Badge
                variant="outline"
                className={`text-[10px] ${
                  ok
                    ? "border-emerald-500/20 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400"
                    : "border-red-500/20 bg-red-500/10 text-red-600 dark:text-red-400"
                }`}
              >
                {row.outcome}
              </Badge>
            </div>
            {row.proposal?.proposal_id != null && (
              <p className="mt-1 text-[10px] text-muted-foreground">
                Proposal #{row.proposal.proposal_id}
              </p>
            )}
          </div>
          <time className="shrink-0 text-[10px] tabular-nums text-muted-foreground">
            <span className="block">{new Date(row.created_at).toLocaleDateString()}</span>
            <span className="block text-right">{new Date(row.created_at).toLocaleTimeString()}</span>
          </time>
        </div>
      </div>
    </div>
  );
}

// ── Empty state ───────────────────────────────────────────────────────────────

function EmptyAudit() {
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-20 text-center">
      <div className="flex size-10 items-center justify-center rounded-full border bg-muted">
        <RiTimeLine className="size-5 text-muted-foreground" />
      </div>
      <p className="text-sm text-muted-foreground">
        No executions recorded yet.
      </p>
      <p className="text-xs text-muted-foreground">
        Approve a Proposal on the Decisions page to see entries here.
      </p>
    </div>
  );
}

// ── Public component ──────────────────────────────────────────────────────────

export function AuditTimeline() {
  const { data: rows, isLoading, refetch, isFetching } = useAudit();

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <p className="text-xs text-muted-foreground">
          Append-only record of every approved Execution. Cannot be modified.
        </p>
        <Button
          variant="outline"
          size="xs"
          onClick={() => refetch()}
          disabled={isFetching}
        >
          <RiRefreshLine className={`size-3 ${isFetching ? "animate-spin" : ""}`} />
          Refresh
        </Button>
      </div>

      <Separator />

      <ScrollArea className="h-[600px] pr-3">
        {isLoading ? (
          <div className="space-y-4">
            {Array.from({ length: 5 }).map((_, i) => (
              <div key={i} className="flex gap-4">
                <Skeleton className="size-8 shrink-0 rounded-full" />
                <div className="flex-1 space-y-2">
                  <Skeleton className="h-4 w-48" />
                  <Skeleton className="h-3 w-32" />
                </div>
              </div>
            ))}
          </div>
        ) : !rows?.length ? (
          <EmptyAudit />
        ) : (
          <div className="pt-1">
            {rows.map((row, idx) => (
              <AuditEntry
                key={row.id}
                row={row}
                isLast={idx === rows.length - 1}
              />
            ))}
          </div>
        )}
      </ScrollArea>
    </div>
  );
}
