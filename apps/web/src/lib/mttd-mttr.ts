/**
 * MTTD / MTTR — how long GuardRail takes to detect a Canary regression, and
 * how long an escalation then waits for a human.
 *
 * Pure functions over rows already fetched from Postgres. No I/O, no clock
 * (`now` is never needed — every sample is a difference between two stored
 * timestamps), so this is unit-testable without a database.
 *
 * ── What these numbers mean, precisely ────────────────────────────────────────
 *
 * **MTTD is measured from the first failing probe, not from the deploy.**
 * GuardRail's clock starts when a probe ran and the Canary answered 5xx. It
 * cannot see when a bad build was pushed, so this is *evidence-to-verdict*
 * latency, not deploy-to-detect. Labelling it "mean time to detect" without
 * that caveat would overstate what the platform knows.
 *
 * The attribution window is the agent's own: RECENT_WINDOW_SECONDS (1h). A
 * Decision only ever reads an hour back, so an error older than that cannot be
 * what triggered it. Counting it anyway would attribute a week-old failure to
 * today's Decision and inflate MTTD without bound. Escalations with no failing
 * probe inside the window (latency_regress, status_divergence) contribute no
 * sample rather than a fabricated one.
 *
 * **MTTR is measured from the persisted escalation to the Execution.** That
 * interval is almost entirely human: the Proposal set already exists, and
 * nothing happens until someone clicks Execute. It is the number that says
 * whether the approval gate is a speed bump or a queue.
 *
 * Both means skip non-positive samples rather than clamping them to zero — a
 * clock skew or a backdated row should not read as "instant".
 */

/** Mirrors workers/shared/log_row.py ERROR_THRESHOLD. */
export const ERROR_THRESHOLD = 500;

/** Mirrors workers/agent/domain/decision.py RECENT_WINDOW_SECONDS. */
export const RECENT_WINDOW_MS = 3_600_000;

export type MetricRow = {
  timestamp: string;
  service: string;
  status_code: number;
};

export type MetricProposal = {
  id: number | null;
  verdict: string;
  created_at?: string;
};

export type MetricAudit = {
  created_at: string;
  proposal: { proposal_id: number | null } | null;
};

export type DetectionMetrics = {
  /** Mean evidence-to-verdict latency, ms. Null when nothing measurable. */
  mttdMs: number | null;
  mttdSamples: number;
  /** Mean escalation-to-Execution latency, ms. Null when nothing measurable. */
  mttrMs: number | null;
  mttrSamples: number;
  /** Escalations with no failing probe inside the window — excluded from MTTD. */
  unattributed: number;
};

const ms = (iso: string | undefined): number | null => {
  if (!iso) return null;
  const t = Date.parse(iso);
  return Number.isNaN(t) ? null : t;
};

const mean = (xs: number[]): number | null =>
  xs.length === 0
    ? null
    : Math.round(xs.reduce((a, b) => a + b, 0) / xs.length);

export function computeDetectionMetrics(
  logs: MetricRow[],
  proposals: MetricProposal[],
  audit: MetricAudit[],
): DetectionMetrics {
  // ── MTTD: first Canary-only 5xx inside the window, per escalation ──────────
  // Sorted oldest-first once, then scanned per Decision.
  const canaryErrors = logs
    .filter((r) => r.service === "canary" && r.status_code >= ERROR_THRESHOLD)
    .map((r) => ({ at: ms(r.timestamp) ?? 0, row: r }))
    .sort((a, b) => a.at - b.at);

  const detectSamples: number[] = [];
  let unattributed = 0;

  for (const p of proposals) {
    if (p.verdict !== "escalate" || p.id === null) continue;
    const decidedAt = ms(p.created_at);
    if (decidedAt === null) continue;

    // Walk back from the Decision over at most one window of history.
    const from = decidedAt - RECENT_WINDOW_MS;
    let firstFailure: number | null = null;
    for (let i = canaryErrors.length - 1; i >= 0; i--) {
      const at = canaryErrors[i].at;
      if (at > decidedAt) continue;
      if (at >= from) {
        firstFailure = at;
      } else {
        break; // older than the window: no longer attributable
      }
    }

    if (firstFailure === null) {
      unattributed++;
      continue;
    }
    const delta = decidedAt - firstFailure;
    if (delta >= 0) detectSamples.push(delta);
  }

  // ── MTTR: persisted escalation → the Execution that acted on it ───────────
  const decidedAtById = new Map<number, number>();
  for (const p of proposals) {
    const at = ms(p.created_at);
    if (p.id !== null && at !== null) decidedAtById.set(p.id, at);
  }

  const remediateSamples: number[] = [];
  for (const a of audit) {
    const proposalId = a.proposal?.proposal_id ?? null;
    if (proposalId === null) continue;
    const escalatedAt = decidedAtById.get(proposalId);
    const executedAt = ms(a.created_at);
    if (escalatedAt === undefined || executedAt === null) continue;
    const delta = executedAt - escalatedAt;
    if (delta >= 0) remediateSamples.push(delta);
  }

  return {
    mttdMs: mean(detectSamples),
    mttdSamples: detectSamples.length,
    mttrMs: mean(remediateSamples),
    mttrSamples: remediateSamples.length,
    unattributed,
  };
}

/** Human-facing duration. Sub-second reads as "<1s", not "0.4s". */
export function formatDuration(msValue: number | null): string {
  if (msValue === null) return "—";
  if (msValue < 1000) return "<1s";
  const s = msValue / 1000;
  if (s < 60) return `${s < 10 ? s.toFixed(1) : Math.round(s)}s`;
  const m = Math.floor(s / 60);
  const rem = Math.round(s % 60);
  if (m < 60) return rem ? `${m}m ${rem}s` : `${m}m`;
  const h = Math.floor(m / 60);
  return `${h}h ${m % 60}m`;
}
