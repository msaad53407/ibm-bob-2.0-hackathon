"""Criticality map: which endpoint paths matter and how severely a break ranks.

Demo traffic uses the static spec map. Registered external targets derive
tiers from their stored OpenAPI inventory (mutating methods → critical,
reads → high) so analysis follows the connected spec, not ours.
"""
import _paths  # noqa: F401 — ensures shared/ is importable (Docker + repo layouts)
from verification import CRITICALITY as SPEC_CRITICALITY  # noqa: E402

_CRITICAL_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def bob_criticality(spec_dir: str = "docs/spec"):
    """Return the static criticality map (kept name for import compatibility)."""
    return {**SPEC_CRITICALITY, "source": "spec"}


def criticality_from_inventory(inventory: list[dict]) -> dict:
    """Pure map: inventory operations → {critical, high} path prefixes.

    Path templates keep their {params} (decision matching is prefix-based,
    and fired paths share the same prefix up to the template).
    """
    critical, high = [], []
    for op in inventory:
        if not isinstance(op, dict):
            continue
        template = str(op.get("path_template", ""))
        if not template.startswith("/"):
            continue
        # Strip {params}: decision matching is prefix-based, so the static
        # part (/users/ from /users/{id}) is what fired paths share.
        prefix = template.split("{", 1)[0] or "/"
        (critical if op.get("method") in _CRITICAL_METHODS else high).append(prefix)
    return {"critical": critical, "high": high, "source": "target-spec"}
