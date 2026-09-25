"""Probe logic: fire one spec case at one service, build its log row.

No Supabase, no loop — the testable unit. Looping over CASES x SERVICES
lives in runner.main().
"""
import time

import _paths  # noqa: F401 — ensures shared/ is importable
from log_row import make_log_row  # noqa: E402


def fire_case(client, service: str, base: str, method: str, path: str, body: dict | None) -> dict:
    """Fire a single (method, path, body) at base, return its log row."""
    t0 = time.perf_counter()
    try:
        r = client.get(base + path) if method == "GET" else client.post(base + path, json=body)
        return make_log_row(
            service=service,
            endpoint=path,
            status_code=r.status_code,
            latency_ms=int((time.perf_counter() - t0) * 1000),
            error_text=r.text,
        )
    except Exception as e:
        return make_log_row(
            service=service,
            endpoint=path,
            status_code=599,
            latency_ms=int((time.perf_counter() - t0) * 1000),
            error_text=str(e),
        )


def collect_rows(client, cases, services: list[tuple[str, str]]) -> list[dict]:
    """Fire every case at every service (CASES x SERVICES)."""
    return [
        fire_case(client, service, base, method, path, body)
        for method, path, body in cases
        for service, base in services
    ]
