"""
Verification spec: the single place that knows WHAT is probed and WHY.

Cross-language note: the TS side has no Verification logic (dashboard only
displays). Both Python modules import this file — never redeclare cases,
tiers, or thresholds locally:
  - workers/traffic-runner/api/app.py executes CASES (Traffic-runner adapter)
  - workers/agent/domain/criticality.py compares against CRITICALITY (Decision adapter)

Each case probes a tier: critical endpoints must never 5xx on Canary while
Stable is clean; high endpoints must not degrade in p95 latency.
"""

# Probe cases: (method, path, body). The edge POST /checkout with {} is the
# known-risky input — Stable answers 400, a regressed Canary answers 500.
CASES: list[tuple[str, str, dict | None]] = [
    ("GET", "/search?q=normal", None),    # high tier baseline
    ("GET", "/search?q=edge", None),      # high tier edge input
    ("POST", "/checkout", {"item_id": "a", "qty": 1}),  # critical tier happy path
    ("POST", "/checkout", {}),            # critical tier edge input
]

# Criticality map: which endpoint paths matter and how severely a break ranks.
CRITICALITY: dict[str, list[str]] = {
    "critical": ["/checkout"],
    "high": ["/search"],
}

# Default canary-vs-stable p95 latency factor before the Decision escalates.
LATENCY_DEGRADATION_FACTOR = 2.0

# Methods whose 5xx is a regression (they change state) vs reads, which are
# latency-sensitive instead. Single definition: the runner stamps probe rows
# with a tier, the synthesizer assigns one, and the agent's criticality map
# derives one — all from here, so they can never drift apart.
CRITICAL_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def tier_for_method(method: str) -> str:
    """Tier for a method: mutating → 'critical', reads → 'high'."""
    return "critical" if method.upper() in CRITICAL_METHODS else "high"

# How many samples per side/endpoint the latency rule needs before it fires.
MIN_SAMPLES = 2
