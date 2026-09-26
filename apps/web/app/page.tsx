"use client";
import { useEffect, useState, useCallback, useRef } from "react";
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
  note: string | null;
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

/** Format milliseconds as "Xs" or "Xm Ys" */
function fmtMs(ms: number): string {
  const s = Math.round(ms / 1000);
  return s < 60 ? `${s}s` : `${Math.floor(s / 60)}m ${s % 60}s`;
}

export default function Page() {
  const [logs, setLogs] = useState<Log[]>([]);
  const [decision, setDecision] = useState<DecisionState>({ status: "idle" });
  const [approveState, setApproveState] = useState<ApproveState>({ status: "idle" });
  const [audit, setAudit] = useState<AuditRow[]>([]);

  // Timer state
  const [escalationTime, setEscalationTime] = useState<number | null>(null);
  const [resolvedTime, setResolvedTime]     = useState<number | null>(null);
  const [elapsed, setElapsed]               = useState<number>(0);
  const tickRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    const sb = getSupabase();
    sb.from("logs").select("*").order("timestamp", { ascending: false }).limit(50)
      .then(({ data }) => data && setLogs(data as Log[]));
    const ch = sb.channel("logs-live")
      .on("postgres_changes", { event: "INSERT", schema: "public", table: "logs" },
        (p) => setLogs((prev) => [p.new as Log, ...prev].slice(0, 50)))
      .subscribe();

    // Load initial audit trail
    fetch(`${AGENT}/audit`).then((r) => r.json()).then((rows) => setAudit(rows as AuditRow[])).catch(() => {});

    return () => { void sb.removeChannel(ch); };
  }, []);

  // Start ticking when escalation is detected, stop when resolved
  useEffect(() => {
    if (escalationTime !== null && resolvedTime === null) {
      tickRef.current = setInterval(() => {
        setElapsed(Date.now() - escalationTime);
      }, 1000);
    } else {
      if (tickRef.current) { clearInterval(tickRef.current); tickRef.current = null; }
    }
    return () => { if (tickRef.current) { clearInterval(tickRef.current); tickRef.current = null; } };
  }, [escalationTime, resolvedTime]);

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
      // Record escalation wall-clock time
      setEscalationTime(t => t ?? Date.now());
      setElapsed(0);
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
      setResolvedTime(Date.now());
      setApproveState({ status: "done", target });
      // Refresh audit trail after execution
      fetch(`${AGENT}/audit`).then((r) => r.json()).then((rows) => setAudit(rows as AuditRow[])).catch(() => {});
    } catch (e) {
      setApproveState({ status: "failed", message: String(e) });
    }
  }

  // MTTD: earliest canary anomaly in existing logs → escalation detection time
  const mttd = (() => {
    if (escalationTime === null) return null;
    const anomalies = logs.filter(l =>
      (l.service === "canary") &&
      (l.status_code >= 500 || l.latency_ms > 500)
    );
    if (anomalies.length === 0) return null;
    const earliest = Math.min(...anomalies.map(l => new Date(l.timestamp).getTime()));
    return Math.max(0, escalationTime - earliest);
  })();

  // MTTR: escalation → resolved
  const mttr = escalationTime !== null && resolvedTime !== null
    ? resolvedTime - escalationTime
    : escalationTime !== null
      ? elapsed   // live ticking
      : null;

  return (
    <main>
      <h1>GuardRail — canary verifier</h1>

      {/* MTTD / MTTR timers */}
      {(mttd !== null || mttr !== null) && (
        <div className="card" style={{ display: "flex", gap: "2rem", alignItems: "center" }}>
          <div>
            <div style={{ fontSize: "0.75em", color: "#57606a", textTransform: "uppercase", letterSpacing: "0.05em" }}>MTTD</div>
            <div style={{ fontSize: "1.5em", fontWeight: "bold", fontVariantNumeric: "tabular-nums" }}>
              {mttd !== null ? fmtMs(mttd) : "—"}
            </div>
            <div style={{ fontSize: "0.7em", color: "#57606a" }}>anomaly → detection</div>
          </div>
          <div style={{ borderLeft: "1px solid #e5e7eb", paddingLeft: "2rem" }}>
            <div style={{ fontSize: "0.75em", color: "#57606a", textTransform: "uppercase", letterSpacing: "0.05em" }}>MTTR</div>
            <div style={{ fontSize: "1.5em", fontWeight: "bold", fontVariantNumeric: "tabular-nums", color: resolvedTime ? "green" : "darkorange" }}>
              {mttr !== null ? fmtMs(mttr) : "—"}
            </div>
            <div style={{ fontSize: "0.7em", color: "#57606a" }}>{resolvedTime ? "resolved ✓" : "escalation → remediation (live)"}</div>
          </div>
        </div>
      )}

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

      {/* Approval checkpoint (human gate) */}
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

      {/* Audit trail */}
      <div className="card">
        <h3>Audit trail</h3>
        <ul>
          {audit.map((a) => (
            <li key={a.id}>{a.created_at} — {a.approver}: {a.action} ({a.outcome})</li>
          ))}
        </ul>
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
