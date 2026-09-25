import asyncio
import os
from fastapi import FastAPI, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel

BUG_PROFILE = os.getenv("BUG_PROFILE", "stable")  # stable | canary
app = FastAPI(title=f"guardrail-demo-{BUG_PROFILE}")

class Checkout(BaseModel):
    item_id: str | None = None
    qty: int = 1

@app.get("/health")
def health():
    return {"ok": True, "profile": BUG_PROFILE}

@app.get("/search")
async def search(q: str = "x"):
    # Bug 2 (canary only): latency injection
    if BUG_PROFILE == "canary":
        await asyncio.sleep(0.8)
    return {"profile": BUG_PROFILE, "q": q, "results": [q]}

@app.post("/checkout")
def checkout(body: Checkout, response: Response):
    # Bug 1 (canary only): 500 on edge case, stable correctly returns 400
    if not body.item_id:
        if BUG_PROFILE == "canary":
            return JSONResponse(status_code=500, content={"error": "boom: item_id missing"})
        response.status_code = 400
        return {"error": "item_id required"}
    return {"ok": True, "profile": BUG_PROFILE, "item_id": body.item_id}
