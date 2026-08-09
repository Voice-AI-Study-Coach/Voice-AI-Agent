"""Cleanup for work the server can no longer finish.

Run on startup. Both jobs exist because a crash or a closed tab leaves rows in
a state nothing else will ever move out of.
"""

import logging
import sys
from datetime import datetime, timedelta, timezone

from backend.config import INGESTION_STUCK_MINUTES, SESSION_IDLE_MINUTES
from src.exception import CustomException
from supabase_client.client import client

log = logging.getLogger(__name__)


def _cutoff(minutes: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(minutes=minutes)).isoformat()


def reap_stuck_documents() -> int:
    """Documents left in 'processing' because the server restarted mid-ingestion.

    Without this they stay in 'processing' forever and the frontend polls a
    status that will never change.
    """
    try:
        response = (
            client.table("documents")
            .update({
                "status": "failed",
                "error": "Ingestion did not complete (server restarted)",
            })
            .eq("status", "processing")
            .lt("created_at", _cutoff(INGESTION_STUCK_MINUTES))
            .execute()
        )
        count = len(response.data or [])
        if count:
            log.info("reaper: marked %d stuck document(s) as failed", count)
        return count
    except Exception as e:
        raise CustomException(e, sys)


def reap_abandoned_sessions() -> int:
    """Sessions the user walked away from.

    Keyed on last_activity_at, not started_at, so a genuinely long session
    that is still being answered is never killed.
    """
    try:
        now = datetime.now(timezone.utc).isoformat()
        response = (
            client.table("sessions")
            .update({"status": "abandoned", "ended_at": now})
            .eq("status", "active")
            .lt("last_activity_at", _cutoff(SESSION_IDLE_MINUTES))
            .execute()
        )
        count = len(response.data or [])
        if count:
            log.info("reaper: marked %d abandoned session(s)", count)
        return count
    except Exception as e:
        raise CustomException(e, sys)


def run_reapers() -> None:
    """Best-effort: a reaper failure must never stop the app from booting."""
    for job in (reap_stuck_documents, reap_abandoned_sessions):
        try:
            job()
        except Exception as e:
            log.warning("reaper %s failed: %s", job.__name__, e)
