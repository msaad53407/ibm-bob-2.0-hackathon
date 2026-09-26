"""Graph routing: conditional edges live here, never inline in the builder.

Only one branch today — skip the Jev call when no API key is configured
(merge already treats jev=None as rules-only). Adding a second branch later
(e.g. advisory vs full-control targets) means one function here, not a
builder rewrite.
"""
from config.settings import TYPESAFE_API_KEY
from workflow.state import AgentState


def should_assess(state: AgentState) -> str:
    """Route after rules: 'assess' when Jev is keyed, else straight to merge."""
    if TYPESAFE_API_KEY and state.get("windowed"):
        return "assess"
    return "merge"
