"""Orchestration: single funnel fetch → window → Decision → Proposal."""
import _paths  # noqa: F401 — ensures shared/ is importable
from log_row import now_iso  # noqa: E402

from criticality import bob_criticality
from decision import build_proposals, run_decision, within_window
from settings import LATENCY_DEGRADATION_FACTOR
from store import fetch_recent_rows, save_proposals, sb
from schemas import ProposalSet


def decide_from_data(
    rows: list[dict],
    crit: dict,
    now: str,
    latency_factor: float = LATENCY_DEGRADATION_FACTOR,
) -> tuple[str, list[str]]:
    """Window the rows, then run the Decision module."""
    return run_decision(within_window(rows, now), crit, latency_factor=latency_factor)


def current_proposal_set() -> ProposalSet:
    """Fetch once, then Decision + Proposal + persistence."""
    rows = fetch_recent_rows(sb())
    crit = bob_criticality()
    verdict, reasons = decide_from_data(rows, crit, now_iso())
    proposals = build_proposals(verdict, reasons)
    pid = save_proposals(sb(), verdict, proposals, reasons)
    return ProposalSet(id=pid, verdict=verdict, reasons=reasons, proposals=proposals)
