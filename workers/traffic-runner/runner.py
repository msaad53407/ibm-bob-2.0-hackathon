"""Fires identical spec-derived cases at stable + canary directly (not via proxy)."""
import os, time, uuid, datetime
import httpx
from supabase import create_client

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

def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()

def main():
    sb = create_client(SUPABASE_URL, SUPABASE_KEY) if SUPABASE_URL and SUPABASE_KEY else None
    rows = []
    with httpx.Client(timeout=10) as c:
        for method, path, body in CASES:
            for service, base in (("stable", STABLE), ("canary", CANARY)):
                trace = str(uuid.uuid4())
                t0 = time.perf_counter()
                try:
                    if method == "GET":
                        r = c.get(base + path)
                    else:
                        r = c.post(base + path, json=body)
                    rows.append({
                        "timestamp": now(), "service": service, "endpoint": path,
                        "status_code": r.status_code,
                        "latency_ms": int((time.perf_counter() - t0) * 1000),
                        "error_message": None if r.status_code < 500 else r.text[:500],
                        "trace_id": trace,
                    })
                except Exception as e:
                    rows.append({
                        "timestamp": now(), "service": service, "endpoint": path,
                        "status_code": 599,
                        "latency_ms": int((time.perf_counter() - t0) * 1000),
                        "error_message": str(e)[:500], "trace_id": trace,
                    })
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
