import asyncio, sys
from fastapi import FastAPI, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Literal


# ── Env validation ─────────────────────────────────────────────────────────────
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    bug_profile: Literal["stable", "canary"] = "stable"
    port: int = 8000


try:
    cfg = Settings()
except Exception as exc:
    print(f"\n❌  Invalid environment variables:\n{exc}\n", file=sys.stderr)
    sys.exit(1)

BUG_PROFILE = cfg.bug_profile
app = FastAPI(title=f"guardrail-demo-{BUG_PROFILE}")

class Checkout(BaseModel):
    item_id: str | None = None
    qty: int = 1

@app.get("/health")
def health():
    return {"ok": True, "profile": BUG_PROFILE}

@app.get("/search")
async def search(q: str = "x"):
    # Planted Canary bug probed by shared/verification.py CASES (high tier):
    # latency injection visible to the p95 rule.
    if BUG_PROFILE == "canary":
        await asyncio.sleep(0.8)
    return {"profile": BUG_PROFILE, "q": q, "results": [q]}

@app.post("/checkout")
def checkout(body: Checkout, response: Response):
    # Planted Canary bug probed by shared/verification.py CASES (critical
    # tier edge input {}): 500 where Stable correctly returns 400.
    if not body.item_id:
        if BUG_PROFILE == "canary":
            return JSONResponse(status_code=500, content={"error": "boom: item_id missing"})
        response.status_code = 400
        return {"error": "item_id required"}
    return {"ok": True, "profile": BUG_PROFILE, "item_id": body.item_id}
