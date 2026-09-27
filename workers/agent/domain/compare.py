"""Pair stable and canary responses to the SAME request, then diff them.

Pure domain logic — no I/O, no HTTP, no Supabase. This is the primitive the
Decision was missing: the traffic-runner fires one identical
`(method, path, body)` at both sides, so pairing those rows is the strongest
signal available and is strictly more informative than comparing blind
per-endpoint aggregates.

Why pairing matters (a real bug this replaces): the old rule bucketed rows by
path prefix and fired only when canary had 5xx and stable had none *for the
whole prefix*. A single shared failure on the same prefix — e.g. one
`GET /todos?limit=<overflow>` case 500ing on both sides — masked twelve
canary-only 500s on `POST /todos` under the same `/todos` prefix. Bucketing by
(method, path, body) makes that impossible: a shared failure and a canary-only
failure can never land in the same bucket.

Interface (test surface, see tests/test_compare.py):
  pair_deltas(rows, crit) -> list[Delta]   # one per request, both sides
  findings(deltas, factor) -> list[Delta]  # the subset worth escalating
"""
import _paths  # noqa: F401 — ensures shared/ is importable
from log_row import ServiceName, is_error  # noqa: E402
from verification import LATENCY_DEGRADATION_FACTOR as SPEC_LATENCY_FACTOR  # noqa: E402
from verification import MIN_SAMPLES as SPEC_MIN_SAMPLES  # noqa: E402

# Per side, per request: guards latency percentiles against single-row noise.
MIN_SAMPLES = SPEC_MIN_SAMPLES

# Finding kinds, worst first. `ok` means the two sides agreed.
CANARY_ERROR = "canary_error"      # canary 5xx, stable did not — a regression
STABLE_ERROR = "stable_error"      # stable 5xx, canary did not — not a regression
SHARED_ERROR = "shared_error"      # both sides 5xx — pre-existing, not a regression
LATENCY_REGRESS = "latency_regress"  # canary p95 above stable p95 x factor
STATUS_DIVERGENCE = "status_divergence"  # sides disagree on status, neither 5xx
OK = "ok"

REGRESSION_KINDS = (CANARY_ERROR, LATENCY_REGRESS)
# Kinds that do not change the verdict but belong in the report.
ADVISORY_KINDS = (SHARED_ERROR, STABLE_ERROR, STATUS_DIVERGENCE)

_RANK = {
    CANARY_ERROR: 0,
    LATENCY_REGRESS: 1,
    STATUS_DIVERGENCE: 2,
    SHARED_ERROR: 3,
    STABLE_ERROR: 4,
    OK: 5,
}


class Delta:
    """One request's outcome on both sides.

    A bucket is (method, path, body-hash): the runner fires the same case to
    stable and canary, so both sides of a Delta are literally the same request.
    """

    __slots__ = ("method", "path", "label", "tier", "source",
                 "n_stable", "n_canary",
                 "stable_statuses", "canary_statuses",
                 "p95_stable", "p95_canary", "kind")

    def __init__(self, *, method: str, path: str, label: str | None,
                 tier: str, source: str | None,
                 n_stable: int, n_canary: int,
                 stable_statuses: tuple[int, ...], canary_statuses: tuple[int, ...],
                 p95_stable: int | None, p95_canary: int | None, kind: str):
        self.method = method
        self.path = path
        self.label = label
        self.tier = tier
        self.source = source
        self.n_stable = n_stable
        self.n_canary = n_canary
        self.stable_statuses = stable_statuses
        self.canary_statuses = canary_statuses
        self.p95_stable = p95_stable
        self.p95_canary = p95_canary
        self.kind = kind

    # ── Derived, for reasons + proposals ─────────────────────────────────────

    @property
    def route(self) -> str:
        """Human-facing route identity, e.g. 'POST /todos'."""
        return f"{self.method} {self.path}"

    @property
    def canary_errors(self) -> int:
        return sum(1 for s in self.canary_statuses if is_error(s))

    @property
    def stable_errors(self) -> int:
        return sum(1 for s in self.stable_statuses if is_error(s))

    @property
    def hit_rate(self) -> float:
        """Share of canary attempts that 5xx'd (0.0 when canary never ran)."""
        return self.canary_errors / self.n_canary if self.n_canary else 0.0

    @property
    def latency_ratio(self) -> float | None:
        """canary p95 / stable p95, or None when stable had no samples."""
        if self.p95_stable is None or self.p95_canary is None or not self.p95_stable:
            return None
        return self.p95_canary / self.p95_stable

    @property
    def is_regression(self) -> bool:
        return self.kind in REGRESSION_KINDS

    def to_dict(self) -> dict:
        return {
            "method": self.method, "path": self.path, "label": self.label,
            "tier": self.tier, "source": self.source, "kind": self.kind,
            "n_stable": self.n_stable, "n_canary": self.n_canary,
            "stable_statuses": list(self.stable_statuses),
            "canary_statuses": list(self.canary_statuses),
            "p95_stable": self.p95_stable, "p95_canary": self.p95_canary,
        }

    def __repr__(self) -> str:  # pragma: no cover — debugging aid
        return f"<Delta {self.kind} {self.route} n={self.n_stable}/{self.n_canary}>"


def path_of(endpoint: str) -> str:
    """Strip the query string: '/todos?limit=1' -> '/todos'."""
    return endpoint.split("?", 1)[0]


def request_key(row: dict) -> tuple:
    """Bucket key for one row: same request on the same route + same input.

    `case_label` is the runner's case identity, so two rows of the same case
    collapse into one bucket even if the URL encoding differs. Rows without
    attribution (demo traffic) fall back to the exact path with query.
    """
    label = row.get("case_label")
    path = path_of(row["endpoint"]) if label else row["endpoint"]
    return (row.get("case_method") or "", path, label or row["endpoint"])


def percentile(values: list[int], q: float) -> int:
    """Safe percentile over a list: clamps instead of indexing out."""
    if not values:
        raise ValueError("percentile() of empty list")
    ordered = sorted(values)
    idx = min(int(len(ordered) * q), len(ordered) - 1)
    return ordered[idx]


def tier_of(crit: dict, path: str) -> str:
    """'critical' | 'high' for a path, from the criticality map's prefixes."""
    for tier in ("critical", "high"):
        for prefix in crit.get(tier, []):
            if path_of(path).startswith(prefix):
                return tier
    return "high"


def _classify(d: Delta, latency_factor: float) -> str:
    """Decide a bucket's kind. Errors first — a 5xx outranks any latency story."""
    c_err, s_err = d.canary_errors, d.stable_errors
    if c_err and s_err:
        return SHARED_ERROR
    if c_err:
        return CANARY_ERROR
    if s_err:
        return STABLE_ERROR
    if d.p95_stable is not None and d.p95_canary is not None:
        if (d.n_stable >= MIN_SAMPLES and d.n_canary >= MIN_SAMPLES
                and d.p95_canary > d.p95_stable * latency_factor):
            return LATENCY_REGRESS
    if set(d.stable_statuses) != set(d.canary_statuses) and d.stable_statuses and d.canary_statuses:
        return STATUS_DIVERGENCE
    return OK


def pair_deltas(rows: list[dict], crit: dict,
                latency_factor: float = SPEC_LATENCY_FACTOR) -> list[Delta]:
    """Pair rows by request and classify each pair. Worst-first ordering.

    `rows` need `service`, `endpoint`, `status_code`, `latency_ms` plus the
    optional `case_label` / `case_tier` / `case_source` attribution columns.
    """
    buckets: dict[tuple, dict] = {}
    for row in rows:
        if row.get("service") not in (ServiceName.STABLE, ServiceName.CANARY):
            continue
        key = request_key(row)
        bucket = buckets.setdefault(key, {
            "stable": [], "canary": [], "tier": row.get("case_tier"),
            "source": row.get("case_source"), "label": row.get("case_label"),
            "method": row.get("case_method") or "",
        })
        bucket[row["service"]].append(row)
        # First attribution seen wins; all rows in a bucket share a case.
        if bucket["tier"] is None:
            bucket["tier"] = row.get("case_tier")
        if bucket["source"] is None:
            bucket["source"] = row.get("case_source")
        if bucket["label"] is None:
            bucket["label"] = row.get("case_label")

    deltas: list[Delta] = []
    for (_method, path, _label), bucket in buckets.items():
        stable, canary = bucket["stable"], bucket["canary"]
        s_lat = [r["latency_ms"] for r in stable]
        c_lat = [r["latency_ms"] for r in canary]
        delta = Delta(
            method=bucket["method"] or "ANY",
            path=path,
            label=bucket["label"],
            tier=bucket["tier"] or tier_of(crit, path),
            source=bucket["source"],
            n_stable=len(stable), n_canary=len(canary),
            stable_statuses=tuple(r["status_code"] for r in stable),
            canary_statuses=tuple(r["status_code"] for r in canary),
            p95_stable=percentile(s_lat, 0.95) if s_lat else None,
            p95_canary=percentile(c_lat, 0.95) if c_lat else None,
            kind=OK,
        )
        delta.kind = _classify(delta, latency_factor)
        deltas.append(delta)

    deltas.sort(key=lambda d: (_RANK[d.kind], d.tier != "critical", d.route))
    return deltas


def findings(deltas: list[Delta]) -> list[Delta]:
    """Regressions only — the subset that can change the verdict."""
    return [d for d in deltas if d.is_regression]


def advisory(deltas: list[Delta]) -> list[Delta]:
    """Non-regressions worth reporting (shared errors, divergences, flips)."""
    return [d for d in deltas if d.kind in ADVISORY_KINDS]
