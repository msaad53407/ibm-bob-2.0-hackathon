"use client";
import { useEffect, useState } from "react";
import { createClient } from "@supabase/supabase-js";

const supabase = createClient(
  process.env.NEXT_PUBLIC_SUPABASE_URL!,
  process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!
);

const AGENT = process.env.NEXT_PUBLIC_AGENT_URL ?? "http://localhost:8003";

type Log = {
  timestamp: string; service: string; endpoint: string;
  status_code: number; latency_ms: number; error_message: string | null;
};

type Proposal = {
  action: string; risk: number; blast_radius: string;
  reversibility: string; execute: { target: "stable" | "canary" } | null;
};

type ProposalSet = {
  id: number | null; verdict: string; reasons: string[]; proposals: Proposal[];
};

type AuditRow = {
  id: number; created_at: string; approver: string;
  action: string; outcome: string;
};

export default function Page() {
  const [logs, setLogs] = useState<Log[]>([]);
  const [set, setSet] = useState<ProposalSet | null>(null);
  const [audit, setAudit] = useState<AuditRow[]>([]);
  const [approver, setApprover] = useState("human");

  async function refresh() {
    const [p, a] = await Promise.all([
      fetch(`${AGENT}/propose`, { method: "POST" }).then((r) => r.json()),
      fetch(`${AGENT}/audit`).then((r) => r.json()).catch(() => []),
    ]);
    setSet(p as ProposalSet);
    setAudit(a as AuditRow[]);
  }

  useEffect(() => {
    void refresh();
    supabase.table("logs").select("*").order("timestamp", { ascending: false }).limit(50)
      .then(({ data }) => data && setLogs(data as Log[]));
    const ch = supabase.channel("logs-live")
      .on("postgres_changes", { event: "INSERT", schema: "public", table: "logs" },
        (p) => setLogs((prev) => [p.new as Log, ...prev].slice(0, 50)))
      .subscribe();
    return () => { void supabase.removeChannel(ch); };
  }, []);

  async function approve(proposal: Proposal) {
    if (!proposal.execute) return;
    await fetch(`${AGENT}/execute`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        target: proposal.execute.target,
        approver: approver.trim() || "human",
        proposal_id: set?.id ?? null,
      }),
    });
    void refresh();
  }

  return (
    <main>
      <h1>GuardRail — canary verifier</h1>
      <div className="card">
        <h3>Decision: {set?.verdict ?? "…"}</h3>
        <ul>
          {(set?.reasons ?? []).map((r) => <li key={r}>{r}</li>)}
        </ul>
      </div>
      <div className="card">
        <h3>Approval checkpoint (human gate)</h3>
        <label>
          Approver:{" "}
          <input value={approver} onChange={(e) => setApprover(e.target.value)} />
        </label>
        {(set?.proposals ?? []).map((p) => (
          <div key={p.action}>
            <span>{p.action} (risk {p.risk}, {p.blast_radius}, {p.reversibility})</span>{" "}
            {p.execute ? (
              <button onClick={() => approve(p)}>Flip to {p.execute.target}</button>
            ) : (
              <em>informational — no flip</em>
            )}
          </div>
        ))}
        {set && set.proposals.length === 0 && <p>No action proposed — canary holds.</p>}
      </div>
      <div className="card">
        <h3>Audit trail</h3>
        <ul>
          {audit.map((a) => (
            <li key={a.id}>{a.created_at} — {a.approver}: {a.action} ({a.outcome})</li>
          ))}
        </ul>
      </div>
      <div className="card">
        <h3>Live logs (Supabase Realtime)</h3>
        <pre>{JSON.stringify(logs.slice(0, 20), null, 2)}</pre>
      </div>
    </main>
  );
}
