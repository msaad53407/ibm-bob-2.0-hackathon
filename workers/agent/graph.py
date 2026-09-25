import json, os, subprocess, sys
from typing import Literal
import httpx
from fastapi import FastAPI, HTTPException
from pydantic import AnyHttpUrl, BaseModel, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from supabase import create_client

# shared/ is placed next to graph.py by the Dockerfile (COPY shared/*.py ./shared/)
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "shared"))
from log_row import ServiceName, is_error, now_iso  # noqa: E402
from verification import CRITICALITY as SPEC_CRITICALITY  # noqa: E402
from verification import LATENCY_DEGRADATION_FACTOR as SPEC_LATENCY_FACTOR  # noqa: E402
from verification import MIN_SAMPLES as SPEC_MIN_SAMPLES  # noqa: E402


# ── Env validation ─────────────────────────────────────────────────────────────
# Fails fast at startup — pydantic-settings raises ValidationError on first import
# if required variables are missing or malformed.
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    supabase_url: AnyHttpUrl
    supabase_service_key: str
    proxy_admin_url: AnyHttpUrl = "http://proxy:8080/admin/route"  # type: ignore[assignment]
    port: int = 8003
    latency_degradation_factor: float = SPEC_LATENCY_FACTOR

    @field_validator("supabase_service_key")
    @classmethod
    def _key_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("SUPABASE_SERVICE_KEY must not be empty")
        return v


try:
    cfg = Settings()
except Exception as exc:
    import sys as _sys
    print(f"\n❌  Missing or invalid environment variables:\n{exc}\n", file=_sys.stderr)
    _sys.exit(1)

SUPABASE_URL = str(cfg.supabase_url)
SUPABASE_KEY = cfg.supabase_service_key
PROXY_ADMIN_URL = str(cfg.proxy_admin_url).rstrip("/")
LATENCY_DEGRADATION_FACTOR = cfg.latency_degradation_factor

app = FastAPI(title="guardrail-agent")

def sb():
    return create_client(SUPABASE_URL, SUPABASE_KEY)

def bob_criticality(spec_dir: str = "docs/spec"):
    """Doc-understanding node: genuinely bob-shell-backed with file fallback."""
    try:
        out = subprocess.run(
            ["bob-shell", "summarize", spec_dir, "--format", "json"],
            capture_output=True, text=True, timeout=30,
        )
        if out.returncode == 0:
            return json.loads(out.stdout)
    except Exception:
        pass
    # fallback criticality map (keeps demo unblocked without Bob access)
    return {**SPEC_CRITICALITY, "source": "fallback"}


# ── Pure decision logic ───────────────────────────────────────────────────────
# The Decision module interface: run_decision() + build_proposals() accept plain
# data and return verdicts. No I/O, no HTTP, no Supabase — the interface is the
# test surface (see test_decision.py). HTTP handlers below are thin adapters.

MIN_SAMPLES = SPEC_MIN_SAMPLES  # per side, per endpoint: guards p95 against single-row noise
RECENT_WINDOW_SECONDS = 3600  # ignore rows older than this in decide/propose
RECENT_FETCH_LIMIT = 200  # newest-first cap per fetch; callers pass explicit limits, not magic numbers

# Domain concept: the only legal Traffic flip targets (ADR-0002).
Target = Literal["stable", "canary"]


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

def _latency_rule(rows: list[dict], ep: str, factor: float = LATENCY_DEGRADATION_FACTOR) -> str | None:
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

def run_decision(rows: list[dict], crit: dict) -> tuple[str, list[str]]:
    """
    Pure decision function: no I/O.

    Args:
        rows:  Recent log rows (dicts with service, endpoint, status_code, latency_ms).
        crit:  Criticality map with keys 'critical' and 'high' (lists of endpoint prefixes).

    Returns:
        (verdict, reasons) where verdict is 'escalate' or 'keep'.
    """
    reasons = []
    for ep in crit.get("critical", ["/checkout"]):
        reason = _error_rule(rows, ep)
        if reason:
            reasons.append(reason)
    for ep in crit.get("high", ["/search"]):
        reason = _latency_rule(rows, ep)
        if reason:
            reasons.append(reason)
    if reasons:
        return "escalate", reasons
    return "keep", ["no critical diff"]


# ── HTTP adapters ─────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"ok": True}

class DecideOut(BaseModel):
    verdict: str
    reasons: list[str]

# ── Adapters (I/O lives here, behind the Decision interface) ─────────────────

def fetch_recent_rows(client, limit: int = RECENT_FETCH_LIMIT) -> list[dict]:
    """Supabase adapter: newest-first log rows for the Decision module."""
    return client.table("logs").select("*").order("timestamp", desc=True).limit(limit).execute().data


def decide_from_data(rows: list[dict], crit: dict, now: str) -> tuple[str, list[str]]:
    """One funnel: window the rows, then run the Decision module."""
    return run_decision(within_window(rows, now), crit)


def flip_proxy(target: Target) -> int:
    """Proxy adapter: Traffic flip Execution, returns the Proxy status code."""
    with httpx.Client(timeout=5) as c:
        return c.post(PROXY_ADMIN_URL, json={"target": target}).status_code


def record_audit(client, approver: str, target: Target, status_code: int, proposal_id: int | None = None) -> None:
    """Audit trail adapter: append-only record of the Execution outcome."""
    client.table("audit").insert({
        "approver": approver, "action": f"flip to {target}",
        "outcome": f"proxy={status_code}",
        "proposal": {"target": target, "proposal_id": proposal_id},
    }).execute()


def save_proposals(client, verdict: str, proposals: list[dict]) -> int | None:
    """Proposal adapter: persist the ranked set, return its id for approval."""
    try:
        data = client.table("proposals").insert(
            {"verdict": verdict, "proposals": proposals}
        ).execute().data
        return data[0]["id"] if data else None
    except Exception:
        return None  # history is advisory — never block the Decision


def _list_recent(client, table: str, limit: int) -> list[dict]:
    """Shared shape behind the history adapters: newest-first rows, [] on failure."""
    try:
        return client.table(table).select("*").order(
            "created_at", desc=True).limit(limit).execute().data
    except Exception:
        return []


def list_proposals(client, limit: int = 10) -> list[dict]:
    """Proposal adapter: recent Proposal sets, newest first."""
    return _list_recent(client, "proposals", limit)


def list_audit(client, limit: int = 20) -> list[dict]:
    """Audit trail adapter: recent Execution records, newest first."""
    return _list_recent(client, "audit", limit)


def get_proposal_set(client, proposal_id: int) -> dict | None:
    """Proposal adapter: fetch one persisted set by id for the approval gate."""
    try:
        data = client.table("proposals").select("*").eq("id", proposal_id).execute().data
        return data[0] if data else None
    except Exception:
        return None


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


@app.post("/decide", response_model=DecideOut)
def decide():
    """HTTP adapter: fetches rows + criticality, delegates to run_decision()."""
    rows = fetch_recent_rows(sb())
    crit = bob_criticality()
    verdict, reasons = decide_from_data(rows, crit, now_iso())
    return {"verdict": verdict, "reasons": reasons}

def build_proposals(verdict: str, reasons: list[str]) -> list[dict]:
    """
    Pure proposal function: derives a ranked proposal list from verdict + reasons.
    No I/O — fully testable without mocks.

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
    # Listed so the dashboard can display context, but not executable via /execute
    if has_latency and not has_5xx:
        proposals.append({
            "action": "investigate canary latency before flipping",
            "risk": 0.0,
            "blast_radius": "none",
            "reversibility": "n/a",
            "execute": None,
        })

    return proposals


class ProposalSet(BaseModel):
    id: int | None
    verdict: str
    reasons: list[str]
    proposals: list[dict]


def current_proposal_set() -> ProposalSet:
    """One funnel: fetch once, then Decision + Proposal + persistence."""
    rows = fetch_recent_rows(sb())
    crit = bob_criticality()
    verdict, reasons = decide_from_data(rows, crit, now_iso())
    proposals = build_proposals(verdict, reasons)
    pid = save_proposals(sb(), verdict, proposals)
    return ProposalSet(id=pid, verdict=verdict, reasons=reasons, proposals=proposals)


@app.post("/propose", response_model=ProposalSet)
def propose():
    """Proposal interface: ranked, persisted set the dashboard approves against."""
    return current_proposal_set()


@app.get("/proposals", response_model=list[dict])
def proposals_history():
    """Proposal interface: recent sets for the Approval checkpoint."""
    return list_proposals(sb())


@app.get("/audit", response_model=list[dict])
def audit_history():
    """Audit trail interface: Execution history for the dashboard."""
    return list_audit(sb())


class Approve(BaseModel):
    target: Target
    approver: str = "human"
    proposal_id: int  # required: Execution accepts only approved Proposal IDs

    @field_validator("approver")
    @classmethod
    def _approver_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("approver must not be empty")
        return v


@app.post("/execute")
def execute(a: Approve):
    """HTTP adapter: gated Traffic flip via the Proxy adapter, outcome to Audit trail."""
    reason = approve_execution(get_proposal_set(sb(), a.proposal_id), a.target)
    if reason is not None:
        raise HTTPException(status_code=422, detail=reason)
    status_code = flip_proxy(a.target)
    record_audit(sb(), a.approver, a.target, status_code, a.proposal_id)
    return {"ok": status_code == 200, "target": a.target}
