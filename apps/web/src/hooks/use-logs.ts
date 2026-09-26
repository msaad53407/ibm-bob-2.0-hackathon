/**
 * Supabase real-time log subscription hook.
 *
 * Bootstraps by fetching the most recent rows, then augments with
 * INSERT events pushed over the Realtime channel.  Components stay
 * simple — they just read `{ rows, isLoading, error }`.
 */
"use client";

import { useEffect, useRef, useState } from "react";
import { getSupabase } from "@/lib/supabase";
import type { LogRow } from "@/types/guardrail";

const INITIAL_LIMIT = 200;

export interface UseLogsOptions {
  /** Filter to a single service (e.g. "stable" | "canary") */
  service?: string;
  /** Max rows to keep in memory (oldest shed first) */
  maxRows?: number;
}

export interface UseLogsResult {
  rows: LogRow[];
  isLoading: boolean;
  error: string | null;
  refresh: () => void;
}

/** Shared query behind initial load and manual refresh. */
async function queryLogs(service: string | undefined): Promise<LogRow[]> {
  let query = getSupabase()
    .from("logs")
    .select("*")
    .order("timestamp", { ascending: false })
    .limit(INITIAL_LIMIT);

  if (service) {
    query = query.eq("service", service);
  }

  const { data, error } = await query;
  if (error) throw error;
  return (data as LogRow[]) ?? [];
}

export function useLogs({
  service,
  maxRows = 500,
}: UseLogsOptions = {}): UseLogsResult {
  const [rows, setRows] = useState<LogRow[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  // Latest cap for the realtime callback (assigned inside the effect below,
  // never during render).
  const maxRowsRef = useRef(maxRows);
  // Monotonic counter so every subscribe gets a FRESH channel topic.
  // supabase-js reuses channel objects by topic: sharing "logs-realtime"
  // across hook instances (stable/canary/all on Verification) or across a
  // StrictMode remount calls .on() on an already-subscribed channel, which
  // throws "cannot add postgres_changes callbacks ... after subscribe()".
  const channelSeq = useRef(0);

  function append(incoming: LogRow[]) {
    setRows((prev) => {
      const merged = [...incoming, ...prev];
      return merged.slice(0, maxRowsRef.current);
    });
  }

  // Manual refresh (event handler) — full loading-state cycle.
  async function fetchInitial() {
    setIsLoading(true);
    setError(null);
    try {
      setRows(await queryLogs(service));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load logs");
    } finally {
      setIsLoading(false);
    }
  }

  useEffect(() => {
    maxRowsRef.current = maxRows;
    let cancelled = false;

    // Initial load: state updates only settle after the await below,
    // never synchronously in the effect body.
    void (async () => {
      try {
        const initial = await queryLogs(service);
        if (cancelled) return;
        setRows(initial);
        setError(null);
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to load logs");
        }
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    })();

    // Subscribe to new inserts on a unique topic per effect run —
    // never reuse a topic that may still be subscribed (see above).
    const sb = getSupabase();
    channelSeq.current += 1;
    const topic = `logs-realtime-${service ?? "all"}-${channelSeq.current}`;
    const channel = sb
      .channel(topic)
      .on(
        "postgres_changes",
        {
          event: "INSERT",
          schema: "public",
          table: "logs",
          ...(service ? { filter: `service=eq.${service}` } : {}),
        },
        (payload) => {
          append([payload.new as LogRow]);
        },
      )
      .subscribe();

    return () => {
      cancelled = true;
      void sb.removeChannel(channel);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [service]);

  return { rows, isLoading, error, refresh: fetchInitial };
}
