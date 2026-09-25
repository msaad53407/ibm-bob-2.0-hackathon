"""Composition root: demo Stable/Canary API (thin route wiring).

Bug behavior lives in bugs.py, env in settings.py, shapes in schemas.py.
Re-exports keep `from app.main import app, BUG_PROFILE, Checkout` working.
"""
from fastapi import FastAPI, Response

from .bugs import checkout_result, search_results
from .schemas import Checkout
from .settings import BUG_PROFILE

__all__ = ["app", "BUG_PROFILE", "Checkout", "health", "search", "checkout"]

app = FastAPI(title=f"guardrail-demo-{BUG_PROFILE}")


@app.get("/health")
def health():
    return {"ok": True, "profile": BUG_PROFILE}


@app.get("/search")
async def search(q: str = "x"):
    return await search_results(BUG_PROFILE, q)


@app.post("/checkout")
def checkout(body: Checkout, response: Response):
    from fastapi.responses import Response as FastAPIResponse

    status, payload = checkout_result(BUG_PROFILE, body.item_id)
    if isinstance(payload, FastAPIResponse):
        return payload
    if status is not None:
        response.status_code = status
    return payload
