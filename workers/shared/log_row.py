"""
Single source of truth for log row construction across all Python workers.

Cross-language spec: packages/contracts/src/index.ts (ServiceName values,
ERROR_THRESHOLD / ERROR_MSG_MAX_LEN, make_log_row semantics). This module is
the only Python implementation — never reimplement per worker.
"""
import datetime
import uuid
from typing import Any

# ── ServiceName ────────────────────────────────────────────────────────────────
# Canonical values for the logs.service field.
# All Python writers (runner, agent) must use these — never bare string literals.
class ServiceName:
    STABLE = "stable"
    CANARY = "canary"
    PROXY_EVENT = "proxy"

    @staticmethod
    def proxy_traffic(target: str) -> str:
        """Returns e.g. 'proxy->stable'. Used by the Node proxy (mirrored here for docs)."""
        return f"proxy->{target}"


# ── Constants ──────────────────────────────────────────────────────────────────
ERROR_THRESHOLD = 500      # status_code >= this is classified as an error
ERROR_MSG_MAX_LEN = 500    # error_message is truncated to this length


# ── Helpers ────────────────────────────────────────────────────────────────────
def is_error(status_code: int) -> bool:
    """True when the status code represents an error (>= ERROR_THRESHOLD)."""
    return status_code >= ERROR_THRESHOLD


def error_msg(text: str | None, status_code: int) -> str | None:
    """
    Returns a truncated error message when the status is an error,
    or None for successful responses.
    """
    if not is_error(status_code):
        return None
    if text is None:
        return f"error status {status_code}"
    return text[:ERROR_MSG_MAX_LEN]


def now_iso() -> str:
    """Current UTC time as an ISO-8601 string."""
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def make_log_row(
    *,
    service: str,
    endpoint: str,
    status_code: int,
    latency_ms: int,
    error_text: str | None = None,
    note: str | None = None,
    trace_id: str | None = None,
) -> dict[str, Any]:
    """
    Constructs a LogRow dict ready for insertion into the logs table.

    Args:
        service:      One of ServiceName.STABLE / CANARY / PROXY_EVENT (or proxy_traffic()).
        endpoint:     Request path (with query string where relevant).
        status_code:  HTTP status code.
        latency_ms:   Elapsed time in milliseconds.
        error_text:   Raw response body or exception string. Truncated automatically.
        note:         Non-error annotation (e.g. Traffic flip events). NULL unless set.
        trace_id:     UUID string. Generated automatically if omitted.
    """
    return {
        "timestamp": now_iso(),
        "service": service,
        "endpoint": endpoint,
        "status_code": status_code,
        "latency_ms": latency_ms,
        "error_message": error_msg(error_text, status_code),
        "note": note,
        "trace_id": trace_id or str(uuid.uuid4()),
    }
