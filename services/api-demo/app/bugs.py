"""Planted canary bugs probed by shared/verification.py CASES.

- high tier (GET /search): latency injection visible to the p95 rule.
- critical tier (POST /checkout {}): 500 where Stable correctly returns 400.
Kept here so route handlers stay thin and the bug surface is explicit.
"""
import asyncio

from fastapi.responses import JSONResponse

CANARY_SEARCH_LATENCY_SECONDS = 0.8


async def search_results(profile: str, q: str) -> dict:
    if profile == "canary":
        await asyncio.sleep(CANARY_SEARCH_LATENCY_SECONDS)
    return {"profile": profile, "q": q, "results": [q]}


def checkout_result(profile: str, item_id: str | None):
    if not item_id:
        if profile == "canary":
            return None, JSONResponse(status_code=500, content={"error": "boom: item_id missing"})
        return 400, {"error": "item_id required"}
    return None, {"ok": True, "profile": profile, "item_id": item_id}
