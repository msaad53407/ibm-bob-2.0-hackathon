"""Proxy adapter: Traffic flip Execution (ADR-0002)."""
import httpx

from config.settings import ADMIN_TOKEN, PROXY_ADMIN_URL


def flip_proxy(target: str) -> int:
    """POST the flip target, return the Proxy status code."""
    with httpx.Client(timeout=5) as c:
        return c.post(
            PROXY_ADMIN_URL,
            json={"target": target},
            headers={"Authorization": f"Bearer {ADMIN_TOKEN}"},
        ).status_code
