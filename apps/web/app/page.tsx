"use client";
import { useEffect, useState } from "react";
import { createClient } from "@supabase/supabase-js";

const supabase = createClient(
  process.env.NEXT_PUBLIC_SUPABASE_URL!,
  process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!
);

type Log = {
  timestamp: string; service: string; endpoint: string;
  status_code: number; latency_ms: number; error_message: string | null;
};

export default function Page() {
  const [logs, setLogs] = useState<Log[]>([]);

  useEffect(() => {
    supabase.table("logs").select("*").order("timestamp", { ascending: false }).limit(50)
      .then(({ data }) => data && setLogs(data as Log[]));
    const ch = supabase.channel("logs-live")
      .on("postgres_changes", { event: "INSERT", schema: "public", table: "logs" },
        (p) => setLogs((prev) => [p.new as Log, ...prev].slice(0, 50)))
      .subscribe();
    return () => { void supabase.removeChannel(ch); };
  }, []);

  async function approve(target: string) {
    await fetch(`${process.env.NEXT_PUBLIC_AGENT_URL ?? "http://localhost:8003"}/execute`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ target, approver: "human" }),
    });
  }

  return (
    <main>
      <h1>GuardRail — canary verifier</h1>
      <div className="card">
        <h3>Approval checkpoint (human gate)</h3>
        <button onClick={() => approve("stable")}>Flip to stable (rollback)</button>{" "}
        <button onClick={() => approve("canary")}>Flip to canary</button>
      </div>
      <div className="card">
        <h3>Live logs (Supabase Realtime)</h3>
        <pre>{JSON.stringify(logs.slice(0, 20), null, 2)}</pre>
      </div>
    </main>
  );
}
