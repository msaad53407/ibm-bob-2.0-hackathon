"""Supabase adapter: client factory + batch log insert + targets/cases."""
from supabase import create_client

from config.settings import SUPABASE_KEY, SUPABASE_URL


def sb():
    return create_client(SUPABASE_URL, SUPABASE_KEY) if SUPABASE_URL and SUPABASE_KEY else None


def save_rows(client, rows: list[dict]) -> None:
    """Batch-insert probe rows into logs. No-op without a client."""
    if client:
        client.table("logs").insert(rows).execute()


def create_target(client, owner_email: str, stable_url: str, canary_url: str,
                  spec_text: str, inventory: list[dict]) -> str:
    """Register an external target pair. Returns its uuid."""
    data = client.table("target_pairs").insert({
        "owner_email": owner_email, "stable_url": stable_url,
        "canary_url": canary_url, "spec_text": spec_text,
        "inventory": inventory, "can_flip": False,
    }).execute().data
    return data[0]["id"]


def save_cases(client, target_id: str, cases: list[dict]) -> int:
    """Persist generated cases for a target. Returns count written."""
    if not cases:
        return 0
    client.table("probe_cases").insert([{
        "target_id": target_id, "method": c["method"], "path": c["path"],
        "body": c["body"], "tier": c["tier"], "source": c["source"],
        "label": c.get("label"),
    } for c in cases]).execute()
    return len(cases)


def get_target(client, target_id: str) -> dict | None:
    """Fetch one target pair by id, or None."""
    data = client.table("target_pairs").select("*").eq("id", target_id).execute().data
    return data[0] if data else None


def list_targets(client, owner_email: str) -> list[dict]:
    """Target pairs owned by an email, newest first."""
    return client.table("target_pairs").select(
        "id,owner_email,stable_url,canary_url,can_flip,created_at"
    ).eq("owner_email", owner_email).order("created_at", desc=True).execute().data


def get_cases(client, target_id: str) -> list[dict]:
    """Stored cases for a target, in creation order."""
    return client.table("probe_cases").select(
        "method,path,body,tier,source,label"
    ).eq("target_id", target_id).order("id").execute().data
