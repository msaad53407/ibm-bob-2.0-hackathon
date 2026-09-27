"""Pure Decision module: no I/O, no HTTP, no Supabase.

Everything here is a function over plain data so it can be unit-tested
directly (see tests/test_decision.py and tests/test_compare.py):

  analyze(rows, crit)                  -> Analysis (deltas, findings, verdict, reasons)
  build_proposals(analysis, advisory)  -> ranked, evidence-backed proposals
  approve_execution(proposal_set, target) -> str | None   (the human gate)

The unit of analysis is the **request**, not the endpoint. The traffic-runner
fires the same (method, path, body) at stable and canary, so
domain/compare.pair_deltas joins the two responses and every rule below reads
those pairs. That is the whole point: "same request, 500 on canary / 422 on
stable" is evidence, "canary p95 is higher" is an aggregate that can be true
for reasons that have nothing to do with the release.
"""
import _paths  # noqa: F401 — ensures shared/ is importable
from verification import LATENCY_DEGRADATION_FACTOR as SPEC_LATENCY_FACTOR  # noqa: E402
from verification import MIN_SAMPLES as SPEC_MIN_SAMPLES  # noqa: E402

from domain.compare import (
    ADVISORY_KINDS, CANARY_ERROR, LATENCY_REGRESS, SHARED_ERROR,
    STATUS_DIVERGENCE, STABLE_ERROR, Delta, advisory, findings, pair_deltas,
    path_of,
)

MIN_SAMPLES = SPEC_MIN_SAMPLES  # per side, per request: guards p95 against single-row noise
RECENT_WINDOW_SECONDS = 3600  # ignore rows older than this in decide/propose

__all__ = [
    "Analysis", "analyze", "build_proposals", "informational_proposals",
    "approve_execution", "decide_from_data", "within_window", "describe",
    "group_deltas", "risk_of", "MIN_SAMPLES", "RECENT_WINDOW_SECONDS", "Delta",
]

# Risk is the SEVERITY OF THE FINDING a proposal addresses — not the chance the
# click fails. A flip that mitigates a 70%-severity canary failure shows 70%.
# Derived from kind x tier x how hard the evidence hits, then capped.
_BASE_RISK = {
    CANARY_ERROR: 0.70,
    LATENCY_REGRESS: 0.30,
    STATUS_DIVERGENCE: 0.20,
    SHARED_ERROR: 0.10,
    STABLE_ERROR: 0.10,
}
_TIER_MULT = {"critical": 1.0, "high": 0.6}
_RISK_CAP = 0.95

# A reason is per (route, kind): six failing cases on one route read as one
# finding, not six.
_MAX_EVIDENCE = 3


def path_of(endpoint: str) -> str:
    """Strip the query string so matching is on path, not '?q=' noise."""
    return endpoint.split("?", 1)[0]


def matches(row_endpoint: str, prefix: str) -> bool:
    """Prefix match on path: '/search' matches '/search?q=e', not '/research'."""
    return path_of(row_endpoint).startswith(prefix)


def within_window(rows: list[dict], now_iso: str, max_age_seconds: int = RECENT_WINDOW_SECONDS) -> list[dict]:
    """Keep rows newer than max_age_seconds. Pure — caller passes `now` for tests."""
    from datetime import datetime

    def _parse(ts: str) -> datetime:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))

    now = _parse(now_iso)
    return [r for r in rows if (now - _parse(r["timestamp"])).total_seconds() <= max_age_seconds]


# ── Describing a finding ──────────────────────────────────────────────────────

def _statuses(values: tuple[int, ...]) -> str:
    """'500' or '200/500' for a set of status codes, in first-seen order."""
    seen: list[int] = []
    for v in values:
        if v not in seen:
            seen.append(v)
    return "/".join(str(v) for v in sorted(seen))


def _case_note(group: list[Delta]) -> str:
    """The case labels behind a finding, deduplicated and bounded."""
    labels: list[str] = []
    for d in group:
        if d.label and d.label not in labels:
            labels.append(d.label)
    if not labels:
        return ""
    shown = ", ".join(labels[:_MAX_EVIDENCE])
    more = f" (+{len(labels) - _MAX_EVIDENCE} more)" if len(labels) > _MAX_EVIDENCE else ""
    return f" [{shown}{more}]"


def _counts(group: list[Delta], side: str) -> tuple[int, int]:
    """(error count, total probes) across a group for one side."""
    errs = sum(d.canary_errors if side == "canary" else d.stable_errors for d in group)
    total = sum(d.n_canary if side == "canary" else d.n_stable for d in group)
    return errs, total


def describe(group: list[Delta]) -> str:
    """One human sentence for a same-route, same-kind group of request pairs."""
    first = group[0]
    route, kind = first.route, first.kind
    c_err, c_n = _counts(group, "canary")
    s_err, s_n = _counts(group, "stable")
    cases = _case_note(group)

    if kind == CANARY_ERROR:
        stable_txt = f"stable answers {_statuses(tuple(s for d in group for s in d.stable_statuses))}"
        return (f"{route} 5xx on canary in {c_err}/{c_n} probes "
                f"({_statuses(tuple(c for d in group for c in d.canary_statuses))}) while "
                f"{stable_txt} ({s_err}/{s_n} errors) — canary-only failure{cases}")
    if kind == LATENCY_REGRESS:
        ratios = [d.latency_ratio for d in group if d.latency_ratio]
        ratio = max(ratios) if ratios else 0.0
        slow = max((d for d in group if d.p95_canary), key=lambda d: d.p95_canary, default=first)
        return (f"{route} p95 latency {slow.p95_canary}ms on canary vs {slow.p95_stable}ms "
                f"stable (+{ratio * 100:.0f}%){cases}")
    if kind == STATUS_DIVERGENCE:
        return (f"{route} status diverges: canary {_statuses(tuple(c for d in group for c in d.canary_statuses))} "
                f"vs stable {_statuses(tuple(s for d in group for s in d.stable_statuses))} "
                f"(neither is a 5xx){cases}")
    if kind == SHARED_ERROR:
        return (f"{route} 5xx on both sides ({c_err}/{c_n} canary, {s_err}/{s_n} stable) — "
                f"pre-existing, not a canary regression{cases}")
    if kind == STABLE_ERROR:
        return (f"{route} 5xx on stable only ({s_err}/{s_n}) — not a canary regression{cases}")
    return f"{route} no difference{cases}"


def group_deltas(deltas: list[Delta]) -> list[list[Delta]]:
    """Collapse request pairs into findings: one group per (route, kind).

    pair_deltas already sorts worst-first, so the first group of a route is
    its most severe kind and groups come out ranked.
    """
    groups: list[list[Delta]] = []
    index: dict[tuple[str, str], list[Delta]] = {}
    for d in deltas:
        if d.kind == "ok":
            continue
        key = (d.route, d.kind)
        bucket = index.get(key)
        if bucket is None:
            bucket = []
            index[key] = bucket
            groups.append(bucket)
        bucket.append(d)
    return groups


# ── Risk ──────────────────────────────────────────────────────────────────────

def _intensity(group: list[Delta], kind: str, latency_factor: float) -> float:
    """How hard the evidence hits, 0..1 — share of canary probes, or magnitude."""
    if kind == LATENCY_REGRESS:
        ratios = [d.latency_ratio for d in group if d.latency_ratio]
        if not ratios:
            return 0.0
        # Just over threshold -> near 0; 10x the factor -> saturated.
        return min(1.0, max(ratios) / latency_factor / 5.0)
    c_err, c_n = _counts(group, "canary")
    if kind in (CANARY_ERROR, SHARED_ERROR, STABLE_ERROR):
        return c_err / c_n if c_n else 0.0
    c_n = sum(d.n_canary for d in group) or 1
    return sum(1 for d in group if d.kind == STATUS_DIVERGENCE) / c_n


def risk_of(group: list[Delta], latency_factor: float) -> float:
    """Finding severity, 0..1: kind x tier x intensity. Capped, never negative."""
    first = group[0]
    base = _BASE_RISK.get(first.kind, 0.1)
    tier = _TIER_MULT.get(first.tier, _TIER_MULT["high"])
    # Intensity is blended, not multiplied: a single failing probe on a
    # critical route is still serious, and a total failure can't reach 1.0.
    return round(min(_RISK_CAP, base * tier * (0.55 + 0.45 * _intensity(group, first.kind, latency_factor))), 2)


# ── Analysis ──────────────────────────────────────────────────────────────────

class Analysis:
    """Everything one decision produced. Pure data — no behaviour needed."""

    __slots__ = ("deltas", "findings", "advisories", "verdict", "reasons", "groups")

    def __init__(self, deltas: list[Delta], verdict: str, reasons: list[str],
                 groups: list[list[Delta]]):
        self.deltas = deltas
        self.findings = findings(deltas)
        self.advisories = advisory(deltas)
        self.verdict = verdict
        self.reasons = reasons
        self.groups = groups

    def to_dict(self) -> dict:
        return {
            "verdict": self.verdict,
            "reasons": self.reasons,
            "deltas": [d.to_dict() for d in self.deltas],
        }


def analyze(rows: list[dict], crit: dict,
            latency_factor: float = SPEC_LATENCY_FACTOR) -> Analysis:
    """Pair the rows, classify each pair, and turn regressions into reasons.

    Any canary-only 5xx or latency regression escalates — on any tier, not just
    the one a rule happened to be written for. Criticality scales severity, it
    no longer decides whether a check runs. Non-regressions (shared errors,
    status flips) stay in the report but out of the verdict.
    """
    deltas = pair_deltas(rows, crit, latency_factor=latency_factor)
    groups = group_deltas(deltas)
    regressions = [g for g in groups if g[0].is_regression]
    others = [g for g in groups if not g[0].is_regression]

    reasons = [describe(g) for g in regressions]
    reasons += [describe(g) for g in others]
    if not reasons:
        paired = sum(d.n_canary for d in deltas)
        return Analysis(deltas, "keep", [f"no canary-only difference across {paired} paired probes"], groups)
    return Analysis(deltas, "escalate" if regressions else "keep", reasons, groups)


# ── Proposals ─────────────────────────────────────────────────────────────────

def _blast_radius(group: list[Delta], kind: str) -> str:
    c_err, c_n = _counts(group, "canary")
    route = group[0].route
    if kind == CANARY_ERROR:
        return f"{route} — {c_err}/{c_n} canary probes 5xx, {len(group)} case type(s)"
    if kind == LATENCY_REGRESS:
        slow = max((d for d in group if d.p95_canary), key=lambda d: d.p95_canary, default=group[0])
        return f"{route} — every request on it (p95 {slow.p95_stable}→{slow.p95_canary}ms)"
    if kind == STATUS_DIVERGENCE:
        return f"{route} — clients see a different status than stable ({len(group)} case type(s))"
    if kind == SHARED_ERROR:
        return f"{route} — {c_err}/{c_n} probes 5xx on both versions"
    return f"{route} — {len(group)} case type(s)"


def _action_for(group: list[Delta], kind: str) -> str:
    route = group[0].route
    if kind == CANARY_ERROR:
        return f"hold canary: {route} 5xxs where stable does not"
    if kind == LATENCY_REGRESS:
        return f"investigate canary latency on {route} before rolling further"
    if kind == STATUS_DIVERGENCE:
        return f"reconcile status codes on {route} between versions"
    if kind == SHARED_ERROR:
        return f"track pre-existing 5xx on {route} (not a canary regression)"
    return f"review {route} — stable is the side that fails"


def build_proposals(analysis: Analysis, *, advisory_only: bool = False,
                    latency_factor: float = SPEC_LATENCY_FACTOR) -> list[dict]:
    """Rank recommendations derived from the findings.

    `advisory_only` is the external-target mode: we have no traffic control, so
    nothing here carries an `execute` and the headline recommendation is a
    recommendation rather than a flip. In demo mode the headline is the
    executable flip, addressed to the traffic proxy, with each finding also
    listed so the report explains *why*.
    """
    if analysis.verdict != "escalate":
        return []

    ranked = sorted(
        [g for g in analysis.groups if g[0].is_regression],
        key=lambda g: -risk_of(g, latency_factor),
    )
    if not ranked:
        return []

    top_risk = max(risk_of(g, latency_factor) for g in ranked)
    routes = sorted({g[0].route for g in ranked})
    kinds = {g[0].kind for g in ranked}
    headline_action = (
        f"hold traffic on stable — canary {routes[0]} regresses"
        if len(routes) == 1 else
        f"hold traffic on stable — canary regresses on {len(routes)} routes"
    )
    if LATENCY_REGRESS in kinds and CANARY_ERROR not in kinds:
        headline_action = (
            f"hold traffic on stable — canary latency regresses on {routes[0]}"
            if len(routes) == 1 else
            f"hold traffic on stable — canary latency regresses on {len(routes)} routes"
        )

    proposals: list[dict] = []

    # Headline: what to do about it, in the actor's own terms.
    if advisory_only:
        proposals.append({
            "action": headline_action,
            "risk": top_risk,
            "blast_radius": "n/a (advisory — we do not control your traffic)",
            "reversibility": "n/a — you control your traffic",
            "execute": None,
            "kind": "advisory_hold",
            "tier": ranked[0][0].tier,
            "evidence": [describe(g) for g in ranked[:_MAX_EVIDENCE]],
        })
    else:
        proposals.append({
            "action": "traffic flip to stable",
            "risk": top_risk,
            "blast_radius": f"proxy only — {len(routes)} route(s) back to stable",
            "reversibility": "instant — flip back to canary at any time",
            "execute": {"target": "stable"},
            "kind": "flip",
            "tier": ranked[0][0].tier,
            "evidence": [describe(g) for g in ranked[:_MAX_EVIDENCE]],
        })

    # Then one recommendation per finding, worst first.
    for group in ranked:
        kind = group[0].kind
        evidence = [describe(group)]
        evidence += [f"canary {_statuses(d.canary_statuses)} vs stable {_statuses(d.stable_statuses)}"
                     for d in group[:_MAX_EVIDENCE]]
        proposals.append({
            "action": _action_for(group, kind),
            "risk": risk_of(group, latency_factor),
            "blast_radius": _blast_radius(group, kind),
            "reversibility": "n/a — no action taken",
            "execute": None,
            "kind": kind,
            "tier": group[0].tier,
            "evidence": evidence,
        })

    return proposals


def informational_proposals(analysis: Analysis, *,
                            latency_factor: float = SPEC_LATENCY_FACTOR) -> list[dict]:
    """Non-regression findings: real bugs, but not canary regressions."""
    groups = [g for g in analysis.groups if g[0].kind in ADVISORY_KINDS]
    out = []
    for group in sorted(groups, key=lambda g: -risk_of(g, latency_factor)):
        kind = group[0].kind
        out.append({
            "action": _action_for(group, kind),
            "risk": risk_of(group, latency_factor),
            "blast_radius": _blast_radius(group, kind),
            "reversibility": "n/a — no action taken",
            "execute": None,
            "kind": kind,
            "tier": group[0].tier,
            "evidence": [describe(group)],
        })
    return out


# ── Human gate ────────────────────────────────────────────────────────────────

def approve_execution(proposal_set: dict | None, target: str) -> str | None:
    """
    Pure approval gate: Execution accepts only approved Proposal IDs.
    Returns None when the flip may proceed, else the rejection reason.
    """
    if proposal_set is None:
        return "unknown proposal_id"
    if proposal_set.get("verdict") != "escalate":
        return "proposal set did not escalate"
    approved = [
        p["execute"]["target"]
        for p in proposal_set.get("proposals", [])
        if p.get("execute") and p["execute"].get("target")
    ]
    if target not in approved:
        return f"target {target!r} not in approved proposals {approved}"
    return None


def decide_from_data(
    rows: list[dict],
    crit: dict,
    now: str,
    latency_factor: float = SPEC_LATENCY_FACTOR,
) -> Analysis:
    """Pure funnel: window the rows, then analyze. Directly unit-tested."""
    return analyze(within_window(rows, now), crit, latency_factor=latency_factor)
