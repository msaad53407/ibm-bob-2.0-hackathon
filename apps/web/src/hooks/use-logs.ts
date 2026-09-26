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

export function useLogs({
  service,
  maxRows = 500,
}: UseLogsOptions = {}): UseLogsResult {
  const [rows, setRows] = useState<LogRow[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  // Stable ref so the realtime callback always has the latest maxRows
  const maxRowsRef = useRef(maxRows);
  maxRowsRef.current = maxRows;

  function append(incoming: LogRow[]) {
    setRows((prev) => {
      const merged = [...incoming, ...prev];
      return merged.slice(0, maxRowsRef.current);
    });
  }

  async function fetchInitial() {
    setIsLoading(true);
    setError(null);
    try {
      const sb = getSupabase();
      let query = sb
        .from("logs")
        .select("*")
        .order("timestamp", { ascending: false })
        .limit(INITIAL_LIMIT);

      if (service) {
        query = query.eq("service", service);
      }

      const { data, error: sbError } = await query;
      if (sbError) throw sbError;
      setRows((data as LogRow[]) ?? []);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load logs");
    } finally {
      setIsLoading(false);
    }
  }

  useEffect(() => {
    void fetchInitial();

    // Subscribe to new inserts
    const sb = getSupabase();
    const channel = sb
      .channel("logs-realtime")
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
      void sb.removeChannel(channel);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [service]);

  return { rows, isLoading, error, refresh: fetchInitial };
}
