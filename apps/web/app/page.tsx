"use client";
import { useEffect, useState, useCallback } from "react";
import { createClient, SupabaseClient } from "@supabase/supabase-js";
export const dynamic = "force-dynamic";

// Lazy singleton — only instantiated in the browser where NEXT_PUBLIC_* vars are defined.
// Module-scope createClient() crashes next build (pre-render) when env vars are absent.
let _supabase: SupabaseClient | null = null;
function getSupabase(): SupabaseClient {
  if (!_supabase) {
    _supabase = createClient(
      process.env.NEXT_PUBLIC_SUPABASE_URL!,
      process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!
    );
  }
  return _supabase;
}

const AGENT = process.env.NEXT_PUBLIC_AGENT_URL ?? "http://localhost:8003";

type Log = {
  timestamp: string; service: string; endpoint: string;
  status_code: number; latency_ms: number; error_message: string | null;
};

type Proposal = {
  action: string; risk: number; blast_radius: string;
  reversibility: string; execute: { target: "stable" | "canary" } | null;
};

type DecisionState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "keep" }
  | { status: "escalate"; proposals: Proposal[] };

type ApproveState =
  | { status: "idle" }
  | { status: "executing" }
  | { status: "done"; target: string }
  | { status: "failed"; message: string };

export default function Page() {
  const [logs, setLogs] = useState<Log[]>([]);
  const [decision, setDecision] = useState<DecisionState>({ status: "idle" });
  const [approveState, setApproveState] = useState<ApproveState>({ status: "idle" });

  useEffect(() => {
    const sb = getSupabase();
    sb.from("logs").select("*").order("timestamp", { ascending: false }).limit(50)
      .then(({ data }) => data && setLogs(data as Log[]));
    const ch = sb.channel("logs-live")
      .on("postgres_changes", { event: "INSERT", schema: "public", table: "logs" },
        (p) => setLogs((prev) => [p.new as Log, ...prev].slice(0, 50)))
      .subscribe();
    return () => { void sb.removeChannel(ch); };
  }, []);

  const checkDecision = useCallback(async () => {
    setDecision({ status: "loading" });
    try {
      const res = await fetch(`${AGENT}/decide`, { method: "POST" });
      if (!res.ok) throw new Error(`/decide returned ${res.status}`);
      const { verdict } = await res.json();
      if (verdict === "keep") {
        setDecision({ status: "keep" });
        return;
      }
      const pRes = await fetch(`${AGENT}/propose`, { method: "POST" });
      if (!pRes.ok) throw new Error(`/propose returned ${pRes.status}`);
      const { proposals } = await pRes.json();
      setDecision({ status: "escalate", proposals });
    } catch (e) {
      setDecision({ status: "error", message: String(e) });
    }
  }, []);

  async function approve(target: string) {
    if (approveState.status === "executing") return;
    setApproveState({ status: "executing" });
    try {
      const res = await fetch(`${AGENT}/execute`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ target, approver: "human" }),
      });
      if (!res.ok) throw new Error(`/execute returned ${res.status}`);
      const { ok } = await res.json();
      if (!ok) throw new Error("proxy flip reported not ok");
      setApproveState({ status: "done", target });
    } catch (e) {
      setApproveState({ status: "failed", message: String(e) });
    }
  }

  return (
    <main>
      <h1>GuardRail — canary verifier</h1>

      {/* Decision panel */}
      <div className="card">
        <h3>Agent decision</h3>
        <button onClick={checkDecision} disabled={decision.status === "loading"}>
          {decision.status === "loading" ? "Checking…" : "Check now"}
        </button>

        {decision.status === "error" && (
          <p style={{ color: "red", marginTop: "0.5rem" }}>
            Error: {decision.message}
          </p>
        )}

        {decision.status === "keep" && (
          <p style={{ color: "green", marginTop: "0.5rem" }}>✓ Canary looks healthy — no action needed.</p>
        )}

        {decision.status === "escalate" && (
          <div style={{ marginTop: "0.75rem" }}>
            <p style={{ color: "darkorange", fontWeight: "bold", margin: "0 0 0.75rem" }}>
              ⚠ Escalate — ranked remediation proposals:
            </p>
            {decision.proposals.map((p, i) => (
              <div key={i} className="card" style={{ marginBottom: "0.5rem" }}>
                <strong>#{i + 1} {p.action}</strong>
                <table style={{ marginTop: "0.4rem", borderCollapse: "collapse", width: "100%" }}>
                  <tbody>
                    <tr><td style={td}>Risk</td><td style={td}>{p.risk}</td></tr>
                    <tr><td style={td}>Blast radius</td><td style={td}>{p.blast_radius}</td></tr>
                    <tr><td style={td}>Reversibility</td><td style={td}>{p.reversibility}</td></tr>
                    <tr>
                      <td style={td}>Executable</td>
                      <td style={td}>
                        {p.execute ? (
                          <button
                            onClick={() => approve(p.execute!.target)}
                            disabled={approveState.status === "executing"}
                            style={{ marginLeft: 0 }}
                          >
                            {approveState.status === "executing"
                              ? "Executing…"
                              : `Approve — flip to ${p.execute.target}`}
                          </button>
                        ) : "display only"}
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
            ))}

            {approveState.status === "done" && (
              <p style={{ color: "green", marginTop: "0.5rem" }}>
                ✓ Flip to <strong>{approveState.target}</strong> executed successfully. Audit row recorded.
              </p>
            )}
            {approveState.status === "failed" && (
              <p style={{ color: "red", marginTop: "0.5rem" }}>
                ✗ Execution failed: {approveState.message}
              </p>
            )}
          </div>
        )}
      </div>

      {/* Approval checkpoint (manual override) */}
      <div className="card">
        <h3>Approval checkpoint (human gate)</h3>
        <button
          onClick={() => approve("stable")}
          disabled={approveState.status === "executing"}
        >Flip to stable (rollback)</button>{" "}
        <button
          onClick={() => approve("canary")}
          disabled={approveState.status === "executing"}
        >Flip to canary</button>
        {approveState.status === "done" && (
          <p style={{ color: "green", marginTop: "0.5rem" }}>
            ✓ Flipped to <strong>{approveState.target}</strong>. Audit row recorded.
          </p>
        )}
        {approveState.status === "failed" && (
          <p style={{ color: "red", marginTop: "0.5rem" }}>
            ✗ Execution failed: {approveState.message}
          </p>
        )}
      </div>

      {/* Live logs */}
      <div className="card">
        <h3>Live logs (Supabase Realtime)</h3>
        <pre>{JSON.stringify(logs.slice(0, 20), null, 2)}</pre>
      </div>
    </main>
  );
}

import type { CSSProperties } from "react";
const td: CSSProperties = {
  padding: "2px 8px 2px 0", verticalAlign: "top", fontSize: "0.9em",
};