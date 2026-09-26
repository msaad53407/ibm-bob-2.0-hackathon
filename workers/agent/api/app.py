"""HTTP layer: FastAPI app + route wiring (thin adapters).

Layout of the agent package:
  api/       this HTTP layer (app + shapes)
  domain/    pure business logic, no I/O (decision, criticality)
  adapters/  I/O to the outside world (store, proxy, jev)
  workflow/  LangGraph graph (state, nodes, edges, builder)
  config/    env validation (settings)
  tests/     unit tests (no Supabase, no HTTP)

Analysis runs as a LangGraph workflow: fetch → rules → (assess?) →
merge → propose. This module only wires HTTP to the workflow.
"""
import _paths  # noqa: F401 — ensures shared/ is importable
import hmac
from fastapi import Depends, FastAPI, Header, HTTPException

from adapters.proxy import flip_proxy
from adapters.store import (
    RECENT_FETCH_LIMIT,
    fetch_recent_rows,
    get_proposal_set,
    list_audit,
    list_proposals,
    record_audit,
    save_proposals,
    sb,
)
from api.schemas import Approve, DecideOut, ProposalSet, Target, TargetBody
from config.settings import ADMIN_TOKEN
from domain.criticality import bob_criticality
from domain.decision import (
    MIN_SAMPLES,
    RECENT_WINDOW_SECONDS,
    approve_execution,
    build_proposals,
    decide_from_data,
    matches,
    path_of,
    percentile,
    run_decision,
    within_window,
)
from workflow import run_analysis

__all__ = [
    "app",
    "sb", "bob_criticality",
    "path_of", "matches", "percentile", "within_window",
    "run_decision", "build_proposals", "approve_execution",
    "decide_from_data", "current_proposal_set", "decide_via_graph", "run_analysis",
    "fetch_recent_rows", "flip_proxy", "record_audit",
    "save_proposals", "list_proposals", "list_audit", "get_proposal_set",
    "DecideOut", "ProposalSet", "Approve", "Target", "TargetBody",
    "MIN_SAMPLES", "RECENT_WINDOW_SECONDS", "RECENT_FETCH_LIMIT",
]

app = FastAPI(title="guardrail-agent")

# No CORS middleware (Slice B): browsers reach the agent only through the
# web server's same-origin /api/agent/* forwarders, so cross-origin browser
# access is intentionally unsupported. Server-to-server calls are unaffected.

# ── HTTP-facing helpers (stable signatures, workflow-backed) ────────────────

def current_proposal_set(target_id: str | None = None) -> ProposalSet:
    """Fetch once, then Decision + Proposal + persistence — via the graph."""
    try:
        out = run_analysis(persist=True, target_id=target_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return ProposalSet(
        id=out.get("proposal_id"), verdict=out["verdict"],
        reasons=out["reasons"], proposals=out["proposals"],
    )


def decide_via_graph(target_id: str | None = None) -> tuple[str, list[str]]:
    """Analyze without persisting (/decide): same graph, persist=False."""
    try:
        out = run_analysis(persist=False, target_id=target_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return out["verdict"], out["reasons"]


@app.get("/health")
def health():
    return {"ok": True}


def verify_admin(authorization: str | None = Header(default=None)) -> None:
    """Shared-secret Bearer gate for mutating/decision routes (Slice A).

    /health and read-only history stay open; POST /decide, /propose,
    /execute require ADMIN_TOKEN. Comparison is timing-safe.
    """
    expected = f"Bearer {ADMIN_TOKEN}"
    if not authorization or not hmac.compare_digest(authorization, expected):
        raise HTTPException(status_code=401, detail="unauthorized")


@app.post("/decide", response_model=DecideOut)
def decide(body: TargetBody | None = None, _: None = Depends(verify_admin)):
    """Analyze via the LangGraph workflow (no persistence)."""
    verdict, reasons = decide_via_graph(body.target_id if body else None)
    return {"verdict": verdict, "reasons": reasons}


@app.post("/propose", response_model=ProposalSet)
def propose(body: TargetBody | None = None, _: None = Depends(verify_admin)):
    """Ranked, persisted set the dashboard approves against."""
    return current_proposal_set(body.target_id if body else None)


@app.get("/proposals", response_model=list[dict])
def proposals_history():
    """Recent sets for the Approval checkpoint."""
    return list_proposals(sb())


@app.get("/audit", response_model=list[dict])
def audit_history():
    """Execution history for the dashboard."""
    return list_audit(sb())


@app.post("/execute")
def execute(a: Approve, _: None = Depends(verify_admin)):
    """Gated Traffic flip via the Proxy adapter, outcome to Audit trail."""
    reason = approve_execution(get_proposal_set(sb(), a.proposal_id), a.target)
    if reason is not None:
        raise HTTPException(status_code=422, detail=reason)
    status_code = flip_proxy(a.target)
    record_audit(sb(), a.approver, a.target, status_code, a.proposal_id, a.target_id)
    return {"ok": status_code == 200, "target": a.target}
