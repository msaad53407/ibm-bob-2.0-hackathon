"""Graph nodes: thin orchestrators over testable units.

Best practice: nodes do no heavy logic themselves — pure work lives in
decision.py / jev.py (unit-tested), I/O in store.py. Nodes just move data
between the state and those units, returning partial state updates.
"""
import _paths  # noqa: F401 — ensures shared/ is importable (Docker + repo layouts)
from log_row import now_iso  # noqa: E402

from adapters.jev import ask_jev, build_questions, merge_verdict, summarize_traffic
from adapters.store import fetch_recent_rows, get_target_inventory, save_proposals, sb
from config.settings import LATENCY_DEGRADATION_FACTOR
from domain.criticality import bob_criticality, criticality_from_inventory
from domain.decision import (
    analyze, build_proposals, informational_proposals, within_window,
)
from workflow.state import AgentState


def fetch_rows(state: AgentState) -> dict:
    """Load target-scoped rows + matching criticality map into the state."""
    client = sb()
    target_id = state.get("target_id")
    crit = bob_criticality()
    if target_id:
        inventory = get_target_inventory(client, target_id)
        if inventory is None:
            raise ValueError(f"unknown target_id: {target_id}")
        crit = criticality_from_inventory(inventory)
    return {
        "rows": fetch_recent_rows(client, target_id=target_id),
        "crit": crit,
        "now": state.get("now") or now_iso(),
    }


def apply_rules(state: AgentState) -> dict:
    """Pair the rows into request deltas and run the deterministic guardrail."""
    windowed = within_window(state.get("rows", []), state["now"])
    result = analyze(windowed, state.get("crit", {}),
                     latency_factor=LATENCY_DEGRADATION_FACTOR)
    return {
        "windowed": windowed,
        "analysis": result,
        "deltas": result.deltas,
        "rules_verdict": result.verdict,
        "rules_reasons": result.reasons,
    }


def assess_jev(state: AgentState) -> dict:
    """One System One call over the paired probe table. Never raises."""
    deltas = state.get("deltas") or []
    questions = build_questions(state.get("crit", {}), deltas)
    answers = ask_jev(summarize_traffic(deltas), questions)
    return {"jev": answers}


def merge(state: AgentState) -> dict:
    """Combine rules + Jev into the final verdict (pure merge_verdict)."""
    verdict, reasons = merge_verdict(
        state.get("rules_verdict", "keep"), state.get("rules_reasons", []), state.get("jev")
    )
    return {"verdict": verdict, "reasons": reasons}


def propose(state: AgentState) -> dict:
    """Build the ranked set; persist only when the caller asked (/propose).

    External targets run in advisory mode: no traffic control, so no proposal
    carries `execute` and the headline is a recommendation to hold on stable.
    """
    analysis = state.get("analysis")
    advisory_only = state.get("target_id") is not None
    proposals = build_proposals(analysis, advisory_only=advisory_only)
    if analysis is not None and state.get("verdict") == "escalate":
        # Pre-existing bugs and status flips ride along with the regressions:
        # real problems, but explicitly not canary regressions.
        proposals += informational_proposals(analysis)
    proposal_id = (
        save_proposals(sb(), state["verdict"], proposals, state.get("reasons", []),
                       target_id=state.get("target_id"))
        if state.get("persist")
        else None
    )
    return {"proposals": proposals, "proposal_id": proposal_id}
