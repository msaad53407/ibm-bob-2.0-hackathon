"""Fires identical spec-derived cases at stable + canary directly (not via proxy)."""
import os, sys, time
import httpx
from supabase import create_client

# shared/ is placed next to runner.py by the Dockerfile (COPY shared/log_row.py ./shared/)
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "shared"))
from log_row import ServiceName, make_log_row  # noqa: E402

STABLE = os.getenv("STABLE_URL", "http://stable:8000")
CANARY = os.getenv("CANARY_URL", "http://canary:8000")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY")
RUN_ONCE = os.getenv("RUN_ONCE", "false").lower() == "true"
INTERVAL_SECONDS = int(os.getenv("INTERVAL_SECONDS", "30"))

CASES = [
    ("GET", "/search?q=normal", None),
    ("GET", "/search?q=edge", None),
    ("POST", "/checkout", {"item_id": "a", "qty": 1}),
    ("POST", "/checkout", {}),  # edge: triggers 500 on canary, 400 on stable
]

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
