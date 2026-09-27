"""Graph assembly: fetch → rules → (assess?) → merge → propose.

Compiled once at import, invoked per request with {"persist": ...}.
No checkpointer: each run is stateless; the human approval gate lives in
the FastAPI layer (proposal_id allowlist), not in graph interrupts — a
deliberate simplification for the demo. Stateful interrupts + Postgres
checkpointer is the documented next step when runs must pause mid-graph.
"""
from langgraph.graph import END, START, StateGraph

from workflow.edges import should_assess
from workflow.nodes import apply_rules, assess_jev, fetch_rows, merge, propose
from workflow.state import AgentState

__all__ = ["AgentState", "build", "run_analysis", "should_assess", "workflow"]


def build():
    """Assemble and compile the agent workflow."""
    builder = StateGraph(AgentState)
    builder.add_node("fetch", fetch_rows)
    builder.add_node("rules", apply_rules)
    builder.add_node("assess", assess_jev)
    builder.add_node("merge", merge)
    builder.add_node("propose", propose)

    builder.add_edge(START, "fetch")
    builder.add_edge("fetch", "rules")
    builder.add_conditional_edges("rules", should_assess, {"assess": "assess", "merge": "merge"})
    builder.add_edge("assess", "merge")
    builder.add_edge("merge", "propose")
    builder.add_edge("propose", END)
    return builder.compile()


workflow = build()


def run_analysis(persist: bool, target_id: str | None = None) -> dict:
    """Run one full pass. persist=True saves the proposal set (/propose)."""
    return workflow.invoke({"persist": persist, "target_id": target_id})
