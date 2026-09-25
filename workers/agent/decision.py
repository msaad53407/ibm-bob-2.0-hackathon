"""Pure Decision module: no I/O, no HTTP, no Supabase.

Interface (test surface, see test_decision.py):
  run_decision() + build_proposals() + approve_execution()
accept plain data and return verdicts/reasons.
"""
import _paths  # noqa: F401 — ensures shared/ is importable
from log_row import ServiceName, is_error  # noqa: E402
from verification import LATENCY_DEGRADATION_FACTOR as SPEC_LATENCY_FACTOR  # noqa: E402
from verification import MIN_SAMPLES as SPEC_MIN_SAMPLES  # noqa: E402

MIN_SAMPLES = SPEC_MIN_SAMPLES  # per side, per endpoint: guards p95 against single-row noise
RECENT_WINDOW_SECONDS = 3600  # ignore rows older than this in decide/propose


def path_of(endpoint: str) -> str:
    """Strip the query string so matching is on path, not '?q=' noise."""
    return endpoint.split("?", 1)[0]


def matches(row_endpoint: str, prefix: str) -> bool:
    """Prefix match on path: '/search' matches '/search?q=e', not '/research'."""
    return path_of(row_endpoint).startswith(prefix)


def percentile(sorted_vals: list[int], q: float) -> int:
    """Safe percentile over a pre-sorted list: clamps instead of indexing out."""
    if not sorted_vals:
        raise ValueError("percentile() of empty list")
    idx = min(int(len(sorted_vals) * q), len(sorted_vals) - 1)
    return sorted_vals[idx]


def within_window(rows: list[dict], now_iso: str, max_age_seconds: int = RECENT_WINDOW_SECONDS) -> list[dict]:
    """Keep rows newer than max_age_seconds. Pure — caller passes `now` for tests."""
    from datetime import datetime

    def _parse(ts: str) -> datetime:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))

    now = _parse(now_iso)
    return [r for r in rows if (now - _parse(r["timestamp"])).total_seconds() <= max_age_seconds]


def _error_rule(rows: list[dict], ep: str) -> str | None:
    """Return a reason string if canary has 5xx errors on ep and stable does not."""
    s_err = [r for r in rows if r["service"] == ServiceName.STABLE and matches(r["endpoint"], ep) and is_error(r["status_code"])]
    c_err = [r for r in rows if r["service"] == ServiceName.CANARY and matches(r["endpoint"], ep) and is_error(r["status_code"])]
    if c_err and not s_err:
        return f"canary 5xx on critical {ep}: {len(c_err)} vs stable 0"
    return None


def _latency_rule(rows: list[dict], ep: str, factor: float = SPEC_LATENCY_FACTOR) -> str | None:
    """Return a reason string if canary p95 latency on ep exceeds stable p95 by factor."""
    s_lat = sorted([r["latency_ms"] for r in rows if r["service"] == ServiceName.STABLE and matches(r["endpoint"], ep)])
    c_lat = sorted([r["latency_ms"] for r in rows if r["service"] == ServiceName.CANARY and matches(r["endpoint"], ep)])
    if len(s_lat) < MIN_SAMPLES or len(c_lat) < MIN_SAMPLES:
        return None
    s_p95 = percentile(s_lat, 0.95)
    c_p95 = percentile(c_lat, 0.95)
    if c_p95 > s_p95 * factor:
        return f"canary p95 latency on high {ep}: {c_p95}ms vs stable {s_p95}ms"
    return None


def run_decision(rows: list[dict], crit: dict, latency_factor: float = SPEC_LATENCY_FACTOR) -> tuple[str, list[str]]:
    """
    Pure decision function: no I/O.

    Args:
        rows: Recent log rows (dicts with service, endpoint, status_code, latency_ms).
        crit: Criticality map with keys 'critical' and 'high' (endpoint prefixes).
        latency_factor: canary-vs-stable p95 factor before escalating (env-overridable).

    Returns:
        (verdict, reasons) where verdict is 'escalate' or 'keep'.
    """
    reasons = []
    for ep in crit.get("critical", ["/checkout"]):
        reason = _error_rule(rows, ep)
        if reason:
            reasons.append(reason)
    for ep in crit.get("high", ["/search"]):
        reason = _latency_rule(rows, ep, factor=latency_factor)
        if reason:
            reasons.append(reason)
    if reasons:
        return "escalate", reasons
    return "keep", ["no critical diff"]


def build_proposals(verdict: str, reasons: list[str]) -> list[dict]:
    """
    Pure proposal function: ranked list from verdict + reasons. No I/O.

    Rules:
    - keep  → empty list
    - escalate due to 5xx  → flip-to-stable (only executable action)
    - escalate due to latency only → flip-to-stable + flag-off note (informational)
    - escalate (any)  → flip-to-stable is always first and always executable
    """
    if verdict == "keep":
        return []

    has_5xx = any("5xx" in r for r in reasons)
    has_latency = any("latency" in r for r in reasons)

    proposals = []

    # Primary: flip to stable — always executable, lowest risk
    proposals.append({
        "action": "traffic flip to stable",
        "risk": 0.1,
        "blast_radius": "proxy only",
        "reversibility": "instant",
        "execute": {"target": "stable"},
    })

    # Secondary: informational note when latency (not 5xx) is the only signal
    if has_latency and not has_5xx:
        proposals.append({
            "action": "investigate canary latency before flipping",
            "risk": 0.0,
            "blast_radius": "none",
            "reversibility": "n/a",
            "execute": None,
        })

    return proposals


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
