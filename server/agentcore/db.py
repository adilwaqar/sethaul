"""
SetuHaul AgentCore — Minimal Database Client

Contains ONLY the DB operations needed by the agent tools at runtime.
Full db.py lives in server/ for the FastAPI backend.
"""

import os
import logging
from typing import Optional

from supabase import create_client, Client

logger = logging.getLogger("sethaul.agentcore.db")

# ---------------------------------------------------------------------------
# Client Initialization
# ---------------------------------------------------------------------------

_client: Optional[Client] = None


def get_client() -> Client:
    """Returns a singleton Supabase client instance."""
    global _client
    if _client is None:
        url = os.environ.get("SUPABASE_URL")
        key = os.environ.get("SUPABASE_KEY")
        if not url or not key:
            raise EnvironmentError(
                "SUPABASE_URL and SUPABASE_KEY must be set in environment variables."
            )
        _client = create_client(url, key)
    return _client


# ---------------------------------------------------------------------------
# Operations used by tools.py
# ---------------------------------------------------------------------------


def create_chat_thread(data: dict) -> dict:
    """Insert a new chat thread record."""
    response = get_client().table("chat_threads").insert(data).execute()
    return response.data[0] if response.data else {}


def create_exception(data: dict) -> dict:
    """Insert a new driver exception record."""
    response = get_client().table("driver_exceptions").insert(data).execute()
    return response.data[0] if response.data else {}


def check_duplicate_exception(dedupe_key: str) -> Optional[dict]:
    """Check if an exception with the same dedupe_key already exists."""
    response = (
        get_client()
        .table("driver_exceptions")
        .select("exception_id, thread_id")
        .eq("dedupe_key", dedupe_key)
        .limit(1)
        .execute()
    )
    return response.data[0] if response.data else None
