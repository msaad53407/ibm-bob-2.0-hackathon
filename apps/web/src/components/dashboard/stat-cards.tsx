"use client";

import { RiRefreshLine } from "@remixicon/react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useAgentHealth, useProxyRoute } from "@/hooks/use-agent-queries";

// ── Proxy target card ─────────────────────────────────────────────────────────

export function ProxyStatusCard() {
  const { data, isLoading, refetch, isFetching } = useProxyRoute();
  const target = data?.target;

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
            Proxy Target
          </CardTitle>
          <Button
            variant="ghost"
            size="icon-xs"
            onClick={() => refetch()}
            disabled={isFetching}
          >
            <RiRefreshLine className={isFetching ? "animate-spin" : ""} />
          </Button>
        </div>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <Skeleton className="h-7 w-24" />
        ) : target ? (
          <div className="flex items-center gap-2">
            <div
              className={`size-2 rounded-full animate-pulse ${
                target === "canary" ? "bg-violet-500" : "bg-blue-500"
              }`}
            />
            <span className="text-2xl font-semibold capitalize">{target}</span>
            <Badge
              variant="outline"
              className={
                target === "canary"
                  ? "border-violet-500/20 bg-violet-500/10 text-violet-600 dark:text-violet-400"
                  : "border-blue-500/20 bg-blue-500/10 text-blue-600 dark:text-blue-400"
              }
            >
              {target === "canary" ? "Canary Active" : "Stable Active"}
            </Badge>
          </div>
        ) : (
          <span className="text-sm text-muted-foreground">Unavailable</span>
        )}
        <p className="mt-1 text-xs text-muted-foreground">
          Live traffic routed to this service
        </p>
      </CardContent>
    </Card>
  );
}

// ── Agent health card ─────────────────────────────────────────────────────────

export function AgentHealthCard() {
  const { data, isLoading, refetch, isFetching } = useAgentHealth();
  const ok = data?.ok;

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
            Agent Health
          </CardTitle>
          <Button
            variant="ghost"
            size="icon-xs"
            onClick={() => refetch()}
            disabled={isFetching}
          >
            <RiRefreshLine className={isFetching ? "animate-spin" : ""} />
          </Button>
        </div>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <Skeleton className="h-7 w-20" />
        ) : (
          <div className="flex items-center gap-2">
            <div
              className={`size-2 rounded-full ${ok ? "bg-emerald-500" : "bg-red-500"}`}
            />
            <span
              className={`text-2xl font-semibold ${
                ok
                  ? "text-emerald-600 dark:text-emerald-400"
                  : "text-red-600 dark:text-red-400"
              }`}
            >
              {ok ? "Healthy" : "Down"}
            </span>
          </div>
        )}
        <p className="mt-1 text-xs text-muted-foreground">Agent API (:8003)</p>
      </CardContent>
    </Card>
  );
}

// ── Generic stat card ─────────────────────────────────────────────────────────

interface StatCardProps {
  title: string;
  value: string | number;
  description?: string;
  icon?: React.ReactNode;
  accent?: "default" | "green" | "red" | "violet";
}

const accentClasses: Record<NonNullable<StatCardProps["accent"]>, string> = {
  default: "text-foreground",
  green: "text-emerald-600 dark:text-emerald-400",
  red: "text-red-600 dark:text-red-400",
  violet: "text-violet-600 dark:text-violet-400",
};

export function StatCard({
  title,
  value,
  description,
  icon,
  accent = "default",
}: StatCardProps) {
  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
            {title}
          </CardTitle>
          {icon && <span className="text-muted-foreground">{icon}</span>}
        </div>
      </CardHeader>
      <CardContent>
        <p className={`text-2xl font-semibold ${accentClasses[accent]}`}>
          {value}
        </p>
        {description && (
          <p className="mt-1 text-xs text-muted-foreground">{description}</p>
        )}
      </CardContent>
    </Card>
  );
}
