"""Criticality map: which endpoint paths matter and how severely a break ranks.

Was bob-shell-backed with a static fallback; the shell branch is removed —
the static spec map is what actually ran in every demo (the subprocess never
succeeds inside the agent container). Per-endpoint tiers will later come from
a connected OpenAPI spec; until then this is the single source of truth.
"""
import _paths  # noqa: F401 — ensures shared/ is importable (Docker + repo layouts)
from verification import CRITICALITY as SPEC_CRITICALITY  # noqa: E402


def bob_criticality(spec_dir: str = "docs/spec"):
    """Return the static criticality map (kept name for import compatibility)."""
    return {**SPEC_CRITICALITY, "source": "spec"}
