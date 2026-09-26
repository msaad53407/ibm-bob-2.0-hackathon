"use client";

import Link from "next/link";
import { RiArrowRightLine } from "@remixicon/react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { VerdictBadge } from "@/components/shared/status-badges";
import { useProposals } from "@/hooks/use-agent-queries";

export function RecentDecisionsCard() {
  const { data, isLoading } = useProposals();
  const proposals = data?.slice(0, 5) ?? [];

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
            Recent Decisions
          </CardTitle>
          <Button variant="ghost" size="xs" render={<Link href="/proposals" />}>
            View all
            <RiArrowRightLine className="size-3" />
          </Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-2">
        {isLoading ? (
          Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="h-9 w-full" />
          ))
        ) : proposals.length === 0 ? (
          <p className="py-4 text-center text-xs text-muted-foreground">
            No decisions recorded yet
          </p>
        ) : (
          proposals.map((p) => (
            <div
              key={p.id ?? p.created_at}
              className="flex items-center justify-between gap-3 rounded border px-3 py-2"
            >
              <div className="flex items-center gap-2 min-w-0">
                <VerdictBadge verdict={p.verdict} />
                <span className="truncate text-xs text-muted-foreground">
                  {p.reasons?.[0] ?? "—"}
                </span>
              </div>
              {p.created_at && (
                <span className="shrink-0 text-[10px] text-muted-foreground">
                  {new Date(p.created_at).toLocaleTimeString()}
                </span>
              )}
            </div>
          ))
        )}
      </CardContent>
    </Card>
  );
}
