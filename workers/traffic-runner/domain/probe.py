"""Probe logic: fire one spec case at one service, build its log row.

Client-agnostic (no httpx/Supabase imports) — the testable unit. Looping
over CASES x SERVICES lives in api/app.py main().
"""
import time

import _paths  # noqa: F401 — ensures shared/ is importable
from log_row import make_log_row  # noqa: E402
from verification import tier_for_method  # noqa: E402

# Methods sent without a JSON body even when the case carries one.
_BODYLESS = {"GET", "HEAD", "DELETE"}

# Statuses that mean "this request never reached a handler" — pure routing
# noise from a case aimed at a path/method the server doesn't serve. Kept out
# of the logs so they can't dilute a real finding.
_ROUTING_NOISE = {404, 405, 501}


def fire_case(
    client,
    service: str,
    base: str,
    method: str,
    path: str,
    body: dict | None,
    *,
    tier: str | None = None,
    source: str | None = None,
    label: str | None = None,
    skip_noise: bool = False,
) -> dict | None:
    """Fire a single (method, path, body) at base, return its log row.

    The real HTTP method is sent — a case that says PUT must not arrive as
    POST, or the handler under test is never reached and every response is a
    405. Returns None for routing noise (404/405/501) when `skip_noise`.
    """
    method = method.upper()
    t0 = time.perf_counter()

    def _latency() -> int:
        return int((time.perf_counter() - t0) * 1000)

    def _row(status_code: int, error_text: str | None) -> dict:
        return make_log_row(
            service=service,
            endpoint=path,
            status_code=status_code,
            latency_ms=_latency(),
            error_text=error_text,
            case_tier=tier,
            case_source=source,
            case_label=label,
            case_method=method,
        )

    payload = None if method in _BODYLESS else body
    try:
        r = client.request(method, base + path, json=payload)
    except Exception as e:
        return _row(599, str(e))
    if skip_noise and r.status_code in _ROUTING_NOISE:
        return None
    return _row(r.status_code, r.text)


def collect_rows(client, cases, services: list[tuple[str, str]]) -> list[dict]:
    """Fire every case at every service (CASES x SERVICES).

    Demo cases are bare (method, path, body) tuples, so attribution is derived
    here from the case itself: the method is recorded verbatim, the tier comes
    from the shared method rule, and the label identifies the case by position.
    That keeps the canonical CASES spec untouched while still giving the
    Decision a pairing key for demo traffic.
    """
    rows = []
    for i, (method, path, body) in enumerate(cases, start=1):
        label = f"demo:{method} {path} #{i}"
        for service, base in services:
            row = fire_case(client, service, base, method, path, body,
                            tier=tier_for_method(method), source="demo",
                            label=label)
            if row is not None:
                rows.append(row)
    return rows
