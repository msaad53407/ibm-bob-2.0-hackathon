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
};

type AuditRow = {
  id: number; created_at: string;
  approver: string; action: string; outcome: string;
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

// Separate state for the manual override card so it doesn't pollute the proposal card
type ManualApproveState =
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
  const [auditRows, setAuditRows] = useState<AuditRow[]>([]);
  const [decision, setDecision] = useState<DecisionState>({ status: "idle" });
  // Proposal card approval (flip triggered from a ranked proposal)
  const [approveState, setApproveState] = useState<ApproveState>({ status: "idle" });
  // Manual override buttons (independent of proposal approval)
  const [manualState, setManualState] = useState<ManualApproveState>({ status: "idle" });

  // Timer state
  const [escalationTime, setEscalationTime] = useState<number | null>(null);
  const [resolvedTime, setResolvedTime]     = useState<number | null>(null);
  const [elapsed, setElapsed]               = useState<number>(0);
  const tickRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    const sb = getSupabase();
    // Logs — live
    sb.from("logs").select("*").order("timestamp", { ascending: false }).limit(50)
      .then(({ data }) => data && setLogs(data as Log[]));
    const chLogs = sb.channel("logs-live")
      .on("postgres_changes", { event: "INSERT", schema: "public", table: "logs" },
        (p) => setLogs((prev) => [p.new as Log, ...prev].slice(0, 50)))
      .subscribe();
    // Audit — live
    sb.from("audit").select("id, created_at, approver, action, outcome")
      .order("created_at", { ascending: false }).limit(20)
      .then(({ data }) => data && setAuditRows(data as AuditRow[]));
    const chAudit = sb.channel("audit-live")
      .on("postgres_changes", { event: "INSERT", schema: "public", table: "audit" },
        (p) => setAuditRows((prev) => [p.new as AuditRow, ...prev].slice(0, 20)))
      .subscribe();
    return () => {
      void sb.removeChannel(chLogs);
      void sb.removeChannel(chAudit);
    };
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

  // Called from proposal card — contributes to MTTR
  async function approveProposal(target: string) {
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
    } catch (e) {
      setApproveState({ status: "failed", message: String(e) });
    }
  }

  // Called from manual override card — does NOT affect MTTR or proposal state
  async function approveManual(target: string) {
    if (manualState.status === "executing") return;
    setManualState({ status: "executing" });
    try {
      const res = await fetch(`${AGENT}/execute`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ target, approver: "human" }),
      });
      if (!res.ok) throw new Error(`/execute returned ${res.status}`);
      const { ok } = await res.json();
      if (!ok) throw new Error("proxy flip reported not ok");
      setManualState({ status: "done", target });
    } catch (e) {
      setManualState({ status: "failed", message: String(e) });
    }
  }

  // MTTD: earliest canary anomaly in the most-recent runner batch → escalation time.
  // "Batch" = within 5 min of the newest log in state (avoids stale historical rows
  // inflating MTTD across multiple demo runs without relying on browser wall-clock).
  const mttd = (() => {
    if (escalationTime === null || logs.length === 0) return null;
    const newestLog = Math.max(...logs.map(l => new Date(l.timestamp).getTime()));
    const batchWindowStart = newestLog - 5 * 60 * 1000;
    const anomalies = logs.filter(l =>
      l.service === "canary" &&
      (l.status_code >= 500 || l.latency_ms > 500) &&
      new Date(l.timestamp).getTime() >= batchWindowStart
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
                           onClick={() => approveProposal(p.execute!.target)}
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
          onClick={() => approveManual("stable")}
          disabled={manualState.status === "executing"}
        >Flip to stable (rollback)</button>{" "}
        <button
          onClick={() => approveManual("canary")}
          disabled={manualState.status === "executing"}
        >Flip to canary</button>
        {manualState.status === "done" && (
          <p style={{ color: "green", marginTop: "0.5rem" }}>
            ✓ Flipped to <strong>{manualState.target}</strong>. Audit row recorded.
          </p>
        )}
        {manualState.status === "failed" && (
          <p style={{ color: "red", marginTop: "0.5rem" }}>
            ✗ Execution failed: {manualState.message}
          </p>
        )}
      </div>

      {/* Audit trail */}
      <div className="card">
        <h3>Audit trail (append-only)</h3>
        {auditRows.length === 0 ? (
          <p style={{ color: "#57606a", fontSize: "0.9em" }}>No audit entries yet — approve a flip to create one.</p>
        ) : (
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.85em" }}>
            <thead>
              <tr>
                <th style={th}>Time</th>
                <th style={th}>Action</th>
                <th style={th}>Approver</th>
                <th style={th}>Outcome</th>
              </tr>
            </thead>
            <tbody>
              {auditRows.map((row) => (
                <tr key={row.id}>
                  <td style={td}>{new Date(row.created_at).toLocaleTimeString()}</td>
                  <td style={td}><strong>{row.action}</strong></td>
                  <td style={td}>{row.approver}</td>
                  <td style={{ ...td, color: row.outcome.includes("200") ? "green" : "darkorange" }}>{row.outcome}</td>
                </tr>
              ))}
            </tbody>
          </table>
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
const th: CSSProperties = {
  padding: "2px 8px 4px 0", verticalAlign: "bottom", fontWeight: 600,
  borderBottom: "1px solid #e5e7eb", textAlign: "left", color: "#57606a",
};
