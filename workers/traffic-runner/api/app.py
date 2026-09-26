"""HTTP layer: fire identical spec cases at stable + canary (not via proxy).

Layout of the traffic-runner package:
  api/       this HTTP layer (app + run loop wiring)
  domain/    probe firing (client-agnostic, unit-testable)
  adapters/  Supabase I/O (store)
  config/    env validation (settings)

Probe spec lives in shared/verification.py (CASES) — never redeclared here.
"""
import hmac
import time
from contextlib import asynccontextmanager

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException

import _paths  # noqa: F401 — ensures shared/ is importable
from log_row import ServiceName  # noqa: E402
from domain.probe import collect_rows
from config.settings import ADMIN_TOKEN, CANARY, INTERVAL_SECONDS, RUN_ONCE, RUN_ON_START, STABLE
from adapters.store import save_rows, sb
from verification import CASES  # noqa: E402 — canonical probe spec

__all__ = [
    "app",
    "CASES", "SERVICES", "STABLE", "CANARY",
    "RUN_ONCE", "RUN_ON_START", "INTERVAL_SECONDS",
    "main", "run_once", "sb", "save_rows", "collect_rows",
]

# Maps ServiceName constants to their base URLs
SERVICES = [
    (ServiceName.STABLE, STABLE),
    (ServiceName.CANARY, CANARY),
]


def run_once() -> list[dict]:
    """Fire CASES x SERVICES once, persist rows, return them."""
    client = sb()
    with httpx.Client(timeout=10) as c:
        rows = collect_rows(c, CASES, SERVICES)
    save_rows(client, rows)
    return rows


def main():
    rows = run_once()
    print(f"wrote {len(rows)} rows")
    for r in rows:
        print(r)


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Preserve compose-up behavior: seed one probe batch on boot so the
    # dashboard has logs without any click. Dashboard triggers add more.
    if RUN_ON_START:
        try:
            main()
        except Exception as exc:
            print(f"startup probe failed (serving anyway): {exc}")
    yield


app = FastAPI(title="guardrail-traffic-runner", lifespan=lifespan)


@app.get("/health")
def health():
    return {"ok": True, "cases": len(CASES), "services": len(SERVICES)}


def verify_admin(authorization: str | None = Header(default=None)) -> None:
    """Shared-secret Bearer gate for POST /run (Slice A pattern).

    /health stays open; /run requires ADMIN_TOKEN. Timing-safe compare.
    """
    expected = f"Bearer {ADMIN_TOKEN}"
    if not authorization or not hmac.compare_digest(authorization, expected):
        raise HTTPException(status_code=401, detail="unauthorized")


@app.post("/run")
def trigger(_: None = Depends(verify_admin)):
    """Dashboard trigger: fire one CASES x SERVICES batch, persist to logs."""
    rows = run_once()
    by_service: dict[str, int] = {}
    for r in rows:
        by_service[r["service"]] = by_service.get(r["service"], 0) + 1
    return {"ok": True, "rows": len(rows), "by_service": by_service}


if __name__ == "__main__":
    if RUN_ONCE:
        main()
    else:
        while True:
            main()
            time.sleep(INTERVAL_SECONDS)
