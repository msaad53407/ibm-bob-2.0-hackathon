"""Supabase adapters: client factory + logs/proposals/audit tables.

History reads never raise — newest-first rows, [] on failure — so a
missing table never blocks the Decision.
"""
from supabase import create_client

from config.settings import SUPABASE_KEY, SUPABASE_URL

RECENT_FETCH_LIMIT = 200  # newest-first cap per fetch


def sb():
    return create_client(SUPABASE_URL, SUPABASE_KEY)


def fetch_recent_rows(client, limit: int = RECENT_FETCH_LIMIT) -> list[dict]:
    """Newest-first log rows for the Decision module."""
    return client.table("logs").select("*").order("timestamp", desc=True).limit(limit).execute().data


def record_audit(client, approver: str, target: str, status_code: int, proposal_id: int | None = None) -> None:
    """Append-only record of the Execution outcome."""
    client.table("audit").insert({
        "approver": approver, "action": f"flip to {target}",
        "outcome": f"proxy={status_code}",
        "proposal": {"target": target, "proposal_id": proposal_id},
    }).execute()


def save_proposals(client, verdict: str, proposals: list[dict], reasons: list[str] | None = None) -> int | None:
    """Persist the ranked set, return its id for approval."""
    try:
        data = client.table("proposals").insert(
            {"verdict": verdict, "proposals": proposals, "reasons": reasons or []}
        ).execute().data
        return data[0]["id"] if data else None
    except Exception:
        return None  # history is advisory — never block the Decision


def _list_recent(client, table: str, limit: int) -> list[dict]:
    """Shared shape behind history adapters: newest-first rows, [] on failure."""
    try:
        return client.table(table).select("*").order(
            "created_at", desc=True).limit(limit).execute().data
    except Exception:
        return []


def list_proposals(client, limit: int = 10) -> list[dict]:
    """Recent Proposal sets, newest first."""
    return _list_recent(client, "proposals", limit)


def list_audit(client, limit: int = 20) -> list[dict]:
    """Recent Execution records, newest first."""
    return _list_recent(client, "audit", limit)


def get_proposal_set(client, proposal_id: int) -> dict | None:
    """Fetch one persisted set by id for the approval gate."""
    try:
        data = client.table("proposals").select("*").eq("id", proposal_id).execute().data
        return data[0] if data else None
    except Exception:
        return None
