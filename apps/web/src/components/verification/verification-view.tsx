"use client";

import { useState } from "react";
import {
  RiCircleFill,
  RiFilterLine,
  RiRefreshLine,
} from "@remixicon/react";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Tabs,
  TabsList,
  TabsTrigger,
  TabsContent,
} from "@/components/ui/tabs";
import { StatusBadge, ServiceBadge } from "@/components/shared/status-badges";
import { useLogs } from "@/hooks/use-logs";
import type { LogRow } from "@/types/guardrail";

// ── Latency pill ──────────────────────────────────────────────────────────────

function LatencyPill({ ms }: { ms: number }) {
  const color =
    ms >= 1000
      ? "text-red-600 dark:text-red-400"
      : ms >= 300
        ? "text-amber-600 dark:text-amber-400"
        : "text-emerald-600 dark:text-emerald-400";
  return <span className={`font-mono text-xs ${color}`}>{ms}ms</span>;
}

// ── Log row ───────────────────────────────────────────────────────────────────

function LogTableRow({ row }: { row: LogRow }) {
  return (
    <TableRow className="text-xs">
      <TableCell className="font-mono text-[10px] text-muted-foreground whitespace-nowrap">
        {new Date(row.timestamp).toLocaleTimeString()}
      </TableCell>
      <TableCell>
        <ServiceBadge service={row.service} />
      </TableCell>
      <TableCell className="font-mono max-w-[200px] truncate" title={row.endpoint}>
        {row.endpoint}
      </TableCell>
      <TableCell>
        <StatusBadge status={row.status_code} />
      </TableCell>
      <TableCell>
        <LatencyPill ms={row.latency_ms} />
      </TableCell>
      <TableCell className="max-w-[220px] truncate text-muted-foreground" title={row.error_message ?? row.note ?? ""}>
        {row.error_message
          ? <span className="text-red-500 dark:text-red-400">{row.error_message}</span>
          : row.note
            ? <span className="text-amber-600 dark:text-amber-400">{row.note}</span>
            : "—"
        }
      </TableCell>
    </TableRow>
  );
}

// ── Skeleton rows ─────────────────────────────────────────────────────────────

function LoadingRows() {
  return (
    <>
      {Array.from({ length: 8 }).map((_, i) => (
        <TableRow key={i}>
          {Array.from({ length: 6 }).map((_, j) => (
            <TableCell key={j}>
              <Skeleton className="h-4 w-full" />
            </TableCell>
          ))}
        </TableRow>
      ))}
    </>
  );
}

// ── Logs table ────────────────────────────────────────────────────────────────

interface LogsTableProps {
  service?: string;
  label: string;
}

function LogsTable({ service, label }: LogsTableProps) {
  const { rows, isLoading, error, refresh } = useLogs({ service });

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <RiCircleFill className="size-2 text-emerald-500 animate-pulse" />
          <span className="text-xs text-muted-foreground">
            Live — {rows.length} rows
          </span>
        </div>
        <Button variant="outline" size="xs" onClick={refresh} disabled={isLoading}>
          <RiRefreshLine className={`size-3 ${isLoading ? "animate-spin" : ""}`} />
          Refresh
        </Button>
      </div>

      {error && (
        <div className="rounded border border-red-500/20 bg-red-500/5 px-3 py-2 text-xs text-red-600 dark:text-red-400">
          {error}
        </div>
      )}

      <ScrollArea className="h-[540px] rounded border">
        <Table>
          <TableHeader className="sticky top-0 bg-background z-10">
            <TableRow className="text-[10px]">
              <TableHead className="w-[90px]">Time</TableHead>
              <TableHead className="w-[100px]">Service</TableHead>
              <TableHead>Endpoint</TableHead>
              <TableHead className="w-[70px]">Status</TableHead>
              <TableHead className="w-[80px]">Latency</TableHead>
              <TableHead>Message</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading ? (
              <LoadingRows />
            ) : rows.length === 0 ? (
              <TableRow>
                <TableCell
                  colSpan={6}
                  className="py-12 text-center text-xs text-muted-foreground"
                >
                  No logs yet for {label}
                </TableCell>
              </TableRow>
            ) : (
              rows.map((row) => <LogTableRow key={row.id} row={row} />)
            )}
          </TableBody>
        </Table>
      </ScrollArea>
    </div>
  );
}

// ── Verification summary bar ──────────────────────────────────────────────────

function VerificationSummary() {
  const { rows } = useLogs({ maxRows: 200 });

  const stableRows = rows.filter((r) => r.service === "stable");
  const canaryRows = rows.filter((r) => r.service === "canary");

  function errorRate(list: LogRow[]) {
    if (!list.length) return null;
    const errors = list.filter((r) => r.status_code >= 500).length;
    return ((errors / list.length) * 100).toFixed(1);
  }

  function p95(list: LogRow[]) {
    if (!list.length) return null;
    const sorted = [...list].sort((a, b) => a.latency_ms - b.latency_ms);
    const idx = Math.min(Math.floor(sorted.length * 0.95), sorted.length - 1);
    return sorted[idx].latency_ms;
  }

  const metrics = [
    {
      label: "Stable error rate",
      value: errorRate(stableRows) != null ? `${errorRate(stableRows)}%` : "—",
      accent: Number(errorRate(stableRows)) > 0 ? "text-red-500" : "text-emerald-500",
    },
    {
      label: "Canary error rate",
      value: errorRate(canaryRows) != null ? `${errorRate(canaryRows)}%` : "—",
      accent: Number(errorRate(canaryRows)) > 0 ? "text-red-500" : "text-emerald-500",
    },
    {
      label: "Stable p95 latency",
      value: p95(stableRows) != null ? `${p95(stableRows)}ms` : "—",
      accent: "",
    },
    {
      label: "Canary p95 latency",
      value: p95(canaryRows) != null ? `${p95(canaryRows)}ms` : "—",
      accent:
        p95(canaryRows) != null && p95(stableRows) != null
          ? p95(canaryRows)! > p95(stableRows)! * 2
            ? "text-red-500"
            : "text-emerald-500"
          : "",
    },
  ];

  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
      {metrics.map((m) => (
        <div key={m.label} className="rounded border px-4 py-3">
          <p className="text-[10px] uppercase tracking-wider text-muted-foreground">
            {m.label}
          </p>
          <p className={`mt-1 font-mono text-lg font-semibold ${m.accent}`}>
            {m.value}
          </p>
        </div>
      ))}
    </div>
  );
}

// ── Public component ──────────────────────────────────────────────────────────

export function VerificationView() {
  return (
    <div className="flex flex-col gap-6">
      <VerificationSummary />
      <Tabs defaultValue="all">
        <TabsList>
          <TabsTrigger value="all">All</TabsTrigger>
          <TabsTrigger value="stable">Stable</TabsTrigger>
          <TabsTrigger value="canary">Canary</TabsTrigger>
        </TabsList>
        <div className="mt-4">
          <TabsContent value="all">
            <LogsTable label="any service" />
          </TabsContent>
          <TabsContent value="stable">
            <LogsTable service="stable" label="stable" />
          </TabsContent>
          <TabsContent value="canary">
            <LogsTable service="canary" label="canary" />
          </TabsContent>
        </div>
      </Tabs>
    </div>
  );
}
