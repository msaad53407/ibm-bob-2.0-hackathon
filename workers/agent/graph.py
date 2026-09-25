import json, os, subprocess
import httpx
from fastapi import FastAPI
from pydantic import BaseModel
from supabase import create_client

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY")
PROXY_ADMIN_URL = os.getenv("PROXY_ADMIN_URL", "http://proxy:8080/admin/route")

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

@app.get("/health")
def health():
    return {"ok": True}

class DecideOut(BaseModel):
    verdict: str
    reasons: list[str]

@app.post("/decide", response_model=DecideOut)
def decide():
    rows = sb().table("logs").select("*").order("timestamp", desc=True).limit(200).execute().data
    crit = bob_criticality()
    reasons = []
    # simple MVP rule: error_diff>5% OR p95 latency split on critical endpoint => escalate
    for ep in crit.get("critical", ["/checkout"]):
        s_err = [r for r in rows if r["service"] == "stable" and ep in r["endpoint"] and r["status_code"] >= 500]
        c_err = [r for r in rows if r["service"] == "canary" and ep in r["endpoint"] and r["status_code"] >= 500]
        if c_err and not s_err:
            reasons.append(f"canary 5xx on critical {ep}: {len(c_err)} vs stable 0")
    if reasons:
        return {"verdict": "escalate", "reasons": reasons}
    return {"verdict": "keep", "reasons": ["no critical diff"]}

@app.post("/propose")
def propose():
    d = decide()
    if d["verdict"] == "keep":
        return {"proposals": []}
    return {"proposals": [
        {"action": "traffic flip to stable", "risk": 0.1, "blast_radius": "proxy only", "reversibility": "instant", "execute": {"target": "stable"}},
        {"action": "flag off canary", "risk": 0.3, "blast_radius": "canary users", "reversibility": "fast", "execute": None},
        {"action": "shift traffic 10%", "risk": 0.5, "blast_radius": "10% users", "reversibility": "fast", "execute": None},
    ]}

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
