"""HTTP layer: fire spec cases at stable + canary (not via proxy).

Layout of the traffic-runner package:
  api/       this HTTP layer (app + run loop wiring)
  domain/    probe firing (client-agnostic) + spec parse + case synthesis
  adapters/  Supabase I/O (store) + LLM enhancement (llm)
  config/    env validation (settings)

Demo traffic uses the canonical CASES from shared/verification.py with
target_id NULL. Registered external targets run their stored cases with
rows tagged by target_id (advisory mode — never actuated).
"""
import hmac
import time
from contextlib import asynccontextmanager

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel

import _paths  # noqa: F401 — ensures shared/ is importable
from log_row import ServiceName  # noqa: E402
from domain.probe import collect_rows, fire_case
from domain.spec_parse import SpecError, parse_spec
from domain.synthesize import MAX_TOTAL_CASES, synthesize_all
from adapters.llm import enhance_with_llm
from config.settings import (
    ADMIN_TOKEN, CANARY, CASE_REPEATS, INTERVAL_SECONDS, LLM_MODEL, LLM_TIMEOUT,
    OPENROUTER_API_KEY, RUN_ONCE, RUN_ON_START, STABLE,
)
from adapters.store import (
    create_target, get_cases, get_target, list_targets, save_cases, save_rows, sb,
)
from verification import CASES  # noqa: E402 — canonical probe spec

__all__ = [
    "app",
    "CASES", "SERVICES", "STABLE", "CANARY",
    "RUN_ONCE", "RUN_ON_START", "INTERVAL_SECONDS", "CASE_REPEATS",
    "main", "run_once", "run_target_once", "sb", "save_rows", "collect_rows",
    "register_target",
]

# Maps ServiceName constants to their base URLs (demo pair)
SERVICES = [
    (ServiceName.STABLE, STABLE),
    (ServiceName.CANARY, CANARY),
]


def run_once() -> list[dict]:
    """Fire demo CASES x SERVICES once, persist rows (target_id NULL)."""
    client = sb()
    with httpx.Client(timeout=10) as c:
        rows = collect_rows(c, CASES, SERVICES)
    save_rows(client, rows)
    return rows


def run_target_once(target_id: str) -> list[dict]:
    """Fire a registered target's stored cases at its own URLs, tag rows.

    Each case is fired CASE_REPEATS times per service so latency percentiles
    have samples, and every row carries the case's tier/source/label — that
    attribution is what lets the Decision pair the same request across
    stable and canary instead of comparing blind aggregates.
    """
    client = sb()
    target = get_target(client, target_id)
    if target is None:
        raise ValueError(f"unknown target_id: {target_id}")
    cases = get_cases(client, target_id)
    services = [(ServiceName.STABLE, target["stable_url"].rstrip("/")),
                (ServiceName.CANARY, target["canary_url"].rstrip("/"))]
    rows = []
    with httpx.Client(timeout=10) as c:
        for case in cases:
            for _ in range(CASE_REPEATS):
                for service, base in services:
                    row = fire_case(
                        c, service, base, case["method"], case["path"], case["body"],
                        tier=case.get("tier"), source=case.get("source"),
                        label=case.get("label"), skip_noise=True,
                    )
                    if row is not None:
                        row["target_id"] = target_id
                        rows.append(row)
    save_rows(client, rows)
    return rows


def _dry_fire_stable(cases: list[dict], stable_url: str) -> list[dict]:
    """Drop cases whose route stable doesn't serve (404/405/501) or can't reach.

    Other 4xx/5xx on stable are kept — validation responses and real findings
    are signal. Only unknown routes and transport errors are noise. The real
    method is used, so a PUT case is judged on the PUT route.
    """
    kept = []
    with httpx.Client(timeout=10) as c:
        for case in cases:
            row = fire_case(c, ServiceName.STABLE, stable_url.rstrip("/"),
                            case["method"], case["path"], case["body"],
                            skip_noise=True)
            if row is not None:
                kept.append(case)
    return kept


def register_target(owner_email: str, stable_url: str, canary_url: str,
                    spec_text: str) -> dict:
    """Parse spec → synth cases → LLM extras → dry-fire filter → persist."""
    try:
        inventory = parse_spec(spec_text)
    except SpecError as exc:
        raise ValueError(str(exc)) from exc
    operations = inventory["operations"]
    # Synth first, uncapped, so the response can say whether the stored set was
    # truncated. A large spec is a real case (30 operations easily exceeds 40
    # cases) and an operator deserves to know their case set is partial.
    every = synthesize_all(operations)
    synth = every[:MAX_TOTAL_CASES]
    llm_cases = _dry_fire_stable(
        enhance_with_llm(operations, api_key=OPENROUTER_API_KEY,
                         model=LLM_MODEL, timeout=LLM_TIMEOUT),
        stable_url.rstrip("/"),
    )
    client = sb()
    target_id = create_target(client, owner_email, stable_url, canary_url,
                              spec_text, operations)
    save_cases(client, target_id, synth + llm_cases)
    return {"target_id": target_id,
            "endpoints": len(operations),
            "synth_cases": len(synth), "llm_cases": len(llm_cases),
            # synth_cases_generated > synth_cases means MAX_TOTAL_CASES clipped the
            # set. Surfaced in the UI — a silently partial case set reads as
            # "GuardRail only found these problems" when it found a third of them.
            "synth_cases_generated": len(every),
            "synth_truncated": len(every) > len(synth)}


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


class RegisterBody(BaseModel):
    owner_email: str
    stable_url: str
    canary_url: str
    spec_text: str


class RunBody(BaseModel):
    target_id: str | None = None


@app.get("/health")
def health():
    return {"ok": True, "cases": len(CASES), "services": len(SERVICES)}


def verify_admin(authorization: str | None = Header(default=None)) -> None:
    """Shared-secret Bearer gate (Slice A pattern). /health stays open."""
    expected = f"Bearer {ADMIN_TOKEN}"
    if not authorization or not hmac.compare_digest(authorization, expected):
        raise HTTPException(status_code=401, detail="unauthorized")


@app.post("/run")
def trigger(body: RunBody | None = None, _: None = Depends(verify_admin)):
    """Dashboard trigger: demo batch (no target_id) or one target's batch."""
    target_id = body.target_id if body else None
    try:
        rows = run_target_once(target_id) if target_id else run_once()
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    by_service: dict[str, int] = {}
    for r in rows:
        by_service[r["service"]] = by_service.get(r["service"], 0) + 1
    return {"ok": True, "rows": len(rows), "by_service": by_service,
            "target_id": target_id}


@app.post("/targets")
def create(body: RegisterBody, _: None = Depends(verify_admin)):
    """Register an external target pair: parse, synthesize, LLM extras, store."""
    for field in ("owner_email", "stable_url", "canary_url"):
        if not getattr(body, field).strip():
            raise HTTPException(status_code=400, detail=f"{field} must not be empty")
    for field in ("stable_url", "canary_url"):
        if not getattr(body, field).startswith(("http://", "https://")):
            raise HTTPException(status_code=400, detail=f"{field} must be an http(s) URL")
    try:
        return register_target(body.owner_email.strip(), body.stable_url.strip(),
                               body.canary_url.strip(), body.spec_text)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/targets")
def list_all(owner: str, _: None = Depends(verify_admin)):
    """Target pairs owned by an email (owner filter required)."""
    if not owner.strip():
        raise HTTPException(status_code=400, detail="owner must not be empty")
    return list_targets(sb(), owner.strip())


@app.get("/targets/{target_id}/cases")
def cases(target_id: str, _: None = Depends(verify_admin)):
    """Stored cases for a target."""
    if get_target(sb(), target_id) is None:
        raise HTTPException(status_code=404, detail="unknown target_id")
    return get_cases(sb(), target_id)


if __name__ == "__main__":
    if RUN_ONCE:
        main()
    else:
        while True:
            main()
            time.sleep(INTERVAL_SECONDS)
