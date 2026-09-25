import json, os, subprocess, sys
import httpx
from fastapi import FastAPI
from pydantic import AnyHttpUrl, BaseModel, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from supabase import create_client

# shared/ is placed next to graph.py by the Dockerfile (COPY shared/log_row.py ./shared/)
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "shared"))
from log_row import ServiceName, is_error  # noqa: E402


# ── Env validation ─────────────────────────────────────────────────────────────
# Fails fast at startup — pydantic-settings raises ValidationError on first import
# if required variables are missing or malformed.
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    supabase_url: AnyHttpUrl
    supabase_service_key: str
    proxy_admin_url: AnyHttpUrl = "http://proxy:8080/admin/route"  # type: ignore[assignment]
    port: int = 8003
    latency_degradation_factor: float = 2.0

    @field_validator("supabase_service_key")
    @classmethod
    def _key_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("SUPABASE_SERVICE_KEY must not be empty")
        return v


try:
    cfg = Settings()
except Exception as exc:
    import sys as _sys
    print(f"\n❌  Missing or invalid environment variables:\n{exc}\n", file=_sys.stderr)
    _sys.exit(1)

SUPABASE_URL = str(cfg.supabase_url)
SUPABASE_KEY = cfg.supabase_service_key
PROXY_ADMIN_URL = str(cfg.proxy_admin_url).rstrip("/")
LATENCY_DEGRADATION_FACTOR = cfg.latency_degradation_factor

app = FastAPI(title="guardrail-agent")

def sb():
    return create_client(SUPABASE_URL, SUPABASE_KEY)

def bob_criticality(spec_dir: str = "docs/spec"):
    """Doc-understanding node: genuinely bob-shell-backed with file fallback."""
    try:
        out = subprocess.run(
            ["bob-shell", "summarize", spec_dir, "--format", "json"],
            capture_output=True, text=True, timeout=30,
        )
        if out.returncode == 0:
            return json.loads(out.stdout)
    except Exception:
        pass
    # fallback criticality map (keeps demo unblocked without Bob access)
    return {"critical": ["/checkout"], "high": ["/search"], "source": "fallback"}


# ── Pure decision logic ───────────────────────────────────────────────────────
# These functions accept plain data (rows list, criticality dict) and return
# reasons. No I/O, no HTTP, no Supabase — fully testable without mocks.

def _error_rule(rows: list[dict], ep: str) -> str | None:
    """Return a reason string if canary has 5xx errors on ep and stable does not."""
    s_err = [r for r in rows if r["service"] == ServiceName.STABLE and ep in r["endpoint"] and is_error(r["status_code"])]
    c_err = [r for r in rows if r["service"] == ServiceName.CANARY and ep in r["endpoint"] and is_error(r["status_code"])]
    if c_err and not s_err:
        return f"canary 5xx on critical {ep}: {len(c_err)} vs stable 0"
    return None

def _latency_rule(rows: list[dict], ep: str, factor: float = LATENCY_DEGRADATION_FACTOR) -> str | None:
    """Return a reason string if canary p95 latency on ep exceeds stable p95 by factor."""
    s_lat = sorted([r["latency_ms"] for r in rows if r["service"] == ServiceName.STABLE and ep in r["endpoint"]])
    c_lat = sorted([r["latency_ms"] for r in rows if r["service"] == ServiceName.CANARY and ep in r["endpoint"]])
    if not s_lat or not c_lat:
        return None
    s_p95 = s_lat[int(len(s_lat) * 0.95)]
    c_p95 = c_lat[int(len(c_lat) * 0.95)]
    if c_p95 > s_p95 * factor:
        return f"canary p95 latency on high {ep}: {c_p95}ms vs stable {s_p95}ms"
    return None

def run_decision(rows: list[dict], crit: dict) -> tuple[str, list[str]]:
    """
    Pure decision function: no I/O.

    Args:
        rows:  Recent log rows (dicts with service, endpoint, status_code, latency_ms).
        crit:  Criticality map with keys 'critical' and 'high' (lists of endpoint prefixes).

    Returns:
        (verdict, reasons) where verdict is 'escalate' or 'keep'.
    """
    reasons = []
    for ep in crit.get("critical", ["/checkout"]):
        reason = _error_rule(rows, ep)
        if reason:
            reasons.append(reason)
    for ep in crit.get("high", ["/search"]):
        reason = _latency_rule(rows, ep)
        if reason:
            reasons.append(reason)
    if reasons:
        return "escalate", reasons
    return "keep", ["no critical diff"]


# ── HTTP adapters ─────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"ok": True}

class DecideOut(BaseModel):
    verdict: str
    reasons: list[str]

@app.post("/decide", response_model=DecideOut)
def decide():
    """HTTP adapter: fetches rows + criticality, delegates to run_decision()."""
    rows = sb().table("logs").select("*").order("timestamp", desc=True).limit(200).execute().data
    crit = bob_criticality()
    verdict, reasons = run_decision(rows, crit)
    return {"verdict": verdict, "reasons": reasons}

def build_proposals(verdict: str, reasons: list[str]) -> list[dict]:
    """
    Pure proposal function: derives a ranked proposal list from verdict + reasons.
    No I/O — fully testable without mocks.

    Rules:
    - keep  → empty list
    - escalate due to 5xx  → flip-to-stable (only executable action)
    - escalate due to latency only → flip-to-stable + flag-off note (informational)
    - escalate (any)  → flip-to-stable is always first and always executable
    """
    if verdict == "keep":
        return []

    has_5xx = any("5xx" in r for r in reasons)
    has_latency = any("latency" in r for r in reasons)

    proposals = []

    # Primary: flip to stable — always executable, lowest risk
    proposals.append({
        "action": "traffic flip to stable",
        "risk": 0.1,
        "blast_radius": "proxy only",
        "reversibility": "instant",
        "execute": {"target": "stable"},
    })

    # Secondary: informational note when latency (not 5xx) is the only signal
    # Listed so the dashboard can display context, but not executable via /execute
    if has_latency and not has_5xx:
        proposals.append({
            "action": "investigate canary latency before flipping",
            "risk": 0.0,
            "blast_radius": "none",
            "reversibility": "n/a",
            "execute": None,
        })

    return proposals


@app.post("/propose")
def propose():
    d = decide()
    return {"proposals": build_proposals(d.verdict, d.reasons)}

class Approve(BaseModel):
    target: str  # stable | canary
    approver: str = "human"

@app.post("/execute")
def execute(a: Approve):
    with httpx.Client(timeout=5) as c:
        r = c.post(PROXY_ADMIN_URL, json={"target": a.target})
    sb().table("audit").insert({
        "approver": a.approver, "action": f"flip to {a.target}",
        "outcome": f"proxy={r.status_code}", "proposal": {"target": a.target},
    }).execute()
    return {"ok": r.status_code == 200, "target": a.target}
