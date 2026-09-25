"""Fires identical spec-derived cases at stable + canary directly (not via proxy)."""
import sys, time
import httpx
from pydantic import AnyHttpUrl, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from supabase import create_client

# shared/ is placed next to runner.py by the Dockerfile (COPY shared/*.py ./shared/)
import os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "shared"))
from log_row import ServiceName, make_log_row  # noqa: E402
from verification import CASES  # noqa: E402 — canonical probe spec, see shared/verification.py


# ── Env validation ─────────────────────────────────────────────────────────────
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    stable_url: AnyHttpUrl = "http://stable:8000"  # type: ignore[assignment]
    canary_url: AnyHttpUrl = "http://canary:8000"  # type: ignore[assignment]
    supabase_url: AnyHttpUrl
    supabase_service_key: str
    run_once: bool = False
    interval_seconds: int = 30

    @field_validator("supabase_service_key")
    @classmethod
    def _key_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("SUPABASE_SERVICE_KEY must not be empty")
        return v


try:
    cfg = Settings()
except Exception as exc:
    print(f"\n❌  Missing or invalid environment variables:\n{exc}\n", file=sys.stderr)
    sys.exit(1)

STABLE           = str(cfg.stable_url).rstrip("/")
CANARY           = str(cfg.canary_url).rstrip("/")
SUPABASE_URL     = str(cfg.supabase_url)
SUPABASE_KEY     = cfg.supabase_service_key
RUN_ONCE         = cfg.run_once
INTERVAL_SECONDS = cfg.interval_seconds

# CASES is the canonical probe spec from shared/verification.py (imported
# above). Do not redeclare probe inputs here.

# Maps ServiceName constants to their base URLs
SERVICES = [
    (ServiceName.STABLE, STABLE),
    (ServiceName.CANARY, CANARY),
]

def main():
    sb = create_client(SUPABASE_URL, SUPABASE_KEY) if SUPABASE_URL and SUPABASE_KEY else None
    rows = []
    with httpx.Client(timeout=10) as c:
        for method, path, body in CASES:
            for service, base in SERVICES:
                t0 = time.perf_counter()
                try:
                    r = c.get(base + path) if method == "GET" else c.post(base + path, json=body)
                    rows.append(make_log_row(
                        service=service,
                        endpoint=path,
                        status_code=r.status_code,
                        latency_ms=int((time.perf_counter() - t0) * 1000),
                        error_text=r.text,
                    ))
                except Exception as e:
                    rows.append(make_log_row(
                        service=service,
                        endpoint=path,
                        status_code=599,
                        latency_ms=int((time.perf_counter() - t0) * 1000),
                        error_text=str(e),
                    ))
    if sb:
        sb.table("logs").insert(rows).execute()
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
