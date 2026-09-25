"""Composition root: fire identical spec cases at stable + canary (not via proxy).

Probe spec lives in shared/verification.py (CASES) — never redeclared here.
Probe firing in probe.py, Supabase I/O in store.py, env in settings.py.
This module only wires them to the run loop.

Re-exports keep `from runner import main, SERVICES, ...` working.
"""
import time

import httpx

import _paths  # noqa: F401 — ensures shared/ is importable
from log_row import ServiceName  # noqa: E402
from probe import collect_rows
from settings import CANARY, INTERVAL_SECONDS, RUN_ONCE, STABLE
from store import save_rows, sb
from verification import CASES  # noqa: E402 — canonical probe spec

__all__ = [
    "CASES", "SERVICES", "STABLE", "CANARY",
    "RUN_ONCE", "INTERVAL_SECONDS",
    "main", "sb", "save_rows", "collect_rows",
]

# Maps ServiceName constants to their base URLs
SERVICES = [
    (ServiceName.STABLE, STABLE),
    (ServiceName.CANARY, CANARY),
]


def main():
    client = sb()
    with httpx.Client(timeout=10) as c:
        rows = collect_rows(c, CASES, SERVICES)
    save_rows(client, rows)
    print(f"wrote {len(rows)} rows")
    for r in rows:
        print(r)


if __name__ == "__main__":
    if RUN_ONCE:
        main()
    else:
        while True:
            main()
            time.sleep(INTERVAL_SECONDS)
