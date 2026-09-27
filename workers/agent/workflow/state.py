"""Agent state: the single TypedDict flowing through every node.

Best practice: one flat state with well-named keys, default (overwrite)
reducers, and control flags (`persist`) carried in-band so the same compiled
graph serves both /decide (analyze only) and /propose (analyze + persist).
"""
from typing import TypedDict


class AgentState(TypedDict, total=False):
    # Control
    persist: bool            # True for /propose (save set), False for /decide
    now: str                 # ISO timestamp for windowing (caller-supplied)
    target_id: str | None    # None → demo traffic; uuid → external target

    # Fetch node output
    rows: list[dict]         # raw recent rows from Supabase
    crit: dict               # criticality map {critical:[...], high:[...]}
    windowed: list[dict]     # rows inside the recency window

    # Rules node output
    deltas: list             # paired stable/canary request pairs, worst first
    analysis: object         # domain.decision.Analysis (verdict + reasons + groups)
    rules_verdict: str       # "escalate" | "keep"
    rules_reasons: list[str]

    # Jev node output (None when key missing or call failed)
    jev: dict | None

    # Merge node output (final)
    verdict: str
    reasons: list[str]

    # Propose node output
    proposals: list[dict]
    proposal_id: int | None
