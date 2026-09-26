"""Supabase adapter: client factory + batch log insert."""
from supabase import create_client

from settings import SUPABASE_KEY, SUPABASE_URL


def sb():
    return create_client(SUPABASE_URL, SUPABASE_KEY) if SUPABASE_URL and SUPABASE_KEY else None


def save_rows(client, rows: list[dict]) -> None:
    """Batch-insert probe rows into logs. No-op without a client."""
    if client:
        client.table("logs").insert(rows).execute()
