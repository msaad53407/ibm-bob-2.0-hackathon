"""Graph nodes: thin orchestrators over testable units.

Best practice: nodes do no heavy logic themselves — pure work lives in
decision.py / jev.py (unit-tested), I/O in store.py. Nodes just move data
between the state and those units, returning partial state updates.
"""
import _paths  # noqa: F401 — ensures shared/ is importable (Docker + repo layouts)
from log_row import now_iso  # noqa: E402

from adapters.jev import ask_jev, build_questions, merge_verdict, summarize_traffic
from adapters.store import fetch_recent_rows, save_proposals, sb
from config.settings import LATENCY_DEGRADATION_FACTOR
from domain.criticality import bob_criticality
from domain.decision import build_proposals, run_decision, within_window
from workflow.state import AgentState


def fetch_rows(state: AgentState) -> dict:
    """Load recent logs + criticality map into the state."""
    client = sb()
    return {
        "rows": fetch_recent_rows(client),
        "crit": bob_criticality(),
        "now": state.get("now") or now_iso(),
    }


def apply_rules(state: AgentState) -> dict:
    """Deterministic guardrail verdict over the windowed rows."""
    windowed = within_window(state.get("rows", []), state["now"])
    verdict, reasons = run_decision(
        windowed, state.get("crit", {}), latency_factor=LATENCY_DEGRADATION_FACTOR
    )
    return {"windowed": windowed, "rules_verdict": verdict, "rules_reasons": reasons}


def assess_jev(state: AgentState) -> dict:
    """One System One call over the traffic summary. Never raises."""
    questions = build_questions(state.get("crit", {}))
    answers = ask_jev(summarize_traffic(state.get("windowed", []), state.get("crit", {})), questions)
    return {"jev": answers}


def merge(state: AgentState) -> dict:
    """Combine rules + Jev into the final verdict (pure merge_verdict)."""
    verdict, reasons = merge_verdict(
        state.get("rules_verdict", "keep"), state.get("rules_reasons", []), state.get("jev")
    )
    return {"verdict": verdict, "reasons": reasons}


def propose(state: AgentState) -> dict:
    """Build the ranked set; persist only when the caller asked (/propose)."""
    proposals = build_proposals(state.get("verdict", "keep"), state.get("reasons", []))
    proposal_id = (
        save_proposals(sb(), state["verdict"], proposals, state.get("reasons", []))
        if state.get("persist")
        else None
    )
    return {"proposals": proposals, "proposal_id": proposal_id}
