"""Composition root: FastAPI app + route wiring (thin adapters).

Pure logic lives in decision.py, orchestration in service.py,
I/O in store.py / proxy.py / criticality.py, shapes in schemas.py,
env in settings.py. This module only wires them to HTTP.

Re-exports keep `from graph import run_decision, ...` working.
"""
import _paths  # noqa: F401 — ensures shared/ is importable
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from log_row import now_iso  # noqa: E402

from criticality import bob_criticality
from decision import (
    MIN_SAMPLES,
    RECENT_WINDOW_SECONDS,
    approve_execution,
    build_proposals,
    matches,
    path_of,
    percentile,
    run_decision,
    within_window,
)
from proxy import flip_proxy
from schemas import Approve, DecideOut, ProposalSet, Target
from service import current_proposal_set, decide_from_data
from store import (
    RECENT_FETCH_LIMIT,
    fetch_recent_rows,
    get_proposal_set,
    list_audit,
    list_proposals,
    record_audit,
    save_proposals,
    sb,
)

__all__ = [
    "app",
    "sb", "bob_criticality",
    "path_of", "matches", "percentile", "within_window",
    "run_decision", "build_proposals", "approve_execution",
    "decide_from_data", "current_proposal_set",
    "fetch_recent_rows", "flip_proxy", "record_audit",
    "save_proposals", "list_proposals", "list_audit", "get_proposal_set",
    "DecideOut", "ProposalSet", "Approve", "Target",
    "MIN_SAMPLES", "RECENT_WINDOW_SECONDS", "RECENT_FETCH_LIMIT",
]

app = FastAPI(title="guardrail-agent")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
def health():
    return {"ok": True}


def _p95(values: list[float]) -> float:
    """Return the 95th-percentile value from a non-empty list."""
    s = sorted(values)
    idx = max(0, int(len(s) * 0.95) - 1)
    return s[idx]

@app.post("/decide", response_model=DecideOut)
def decide():
    """Fetches rows + criticality, delegates to the Decision module."""
    rows = fetch_recent_rows(sb())
    crit = bob_criticality()
    verdict, reasons = decide_from_data(rows, crit, now_iso())
    return {"verdict": verdict, "reasons": reasons}


@app.post("/propose", response_model=ProposalSet)
def propose():
    """Ranked, persisted set the dashboard approves against."""
    return current_proposal_set()


@app.get("/proposals", response_model=list[dict])
def proposals_history():
    """Recent sets for the Approval checkpoint."""
    return list_proposals(sb())


@app.get("/audit", response_model=list[dict])
def audit_history():
    """Execution history for the dashboard."""
    return list_audit(sb())


@app.post("/execute")
def execute(a: Approve):
    """Gated Traffic flip via the Proxy adapter, outcome to Audit trail."""
    reason = approve_execution(get_proposal_set(sb(), a.proposal_id), a.target)
    if reason is not None:
        raise HTTPException(status_code=422, detail=reason)
    status_code = flip_proxy(a.target)
    record_audit(sb(), a.approver, a.target, status_code, a.proposal_id)
    return {"ok": status_code == 200, "target": a.target}
