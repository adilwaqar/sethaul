"""
SetuHaul AgentCore — Strands Tool Definitions

Production-ready tools that the Strands agent can invoke during conversation.
Each tool is decorated with @tool and follows the Strands tool contract.
"""

import uuid
from datetime import datetime
from typing import Optional

from strands import tool

from config import logger
from db import (
    create_chat_thread,
    create_exception,
    check_duplicate_exception,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    """Current timestamp in ISO-8601 format with Asia/Kolkata offset."""
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S+05:30")


def _generate_exception_id() -> str:
    """Generate a unique exception ID with EXC prefix."""
    short_id = uuid.uuid4().hex[:8].upper()
    return f"EXC-{short_id}"


def _build_dedupe_key(
    driver_id: str, shipment_id: Optional[str], reported_at: str
) -> str:
    """
    Build a deduplication key to prevent duplicate exception records.
    Format: DRV006-SHP1006-20260804-0934
    """
    shipment_part = shipment_id if shipment_id else "UNKNOWN"
    try:
        dt = datetime.fromisoformat(reported_at)
        date_part = dt.strftime("%Y%m%d-%H%M")
    except (ValueError, TypeError):
        date_part = datetime.now().strftime("%Y%m%d-%H%M")
    return f"{driver_id}-{shipment_part}-{date_part}"


def _map_issue_to_intent(issue_type: str) -> str:
    """Map issue_type to chat_threads.thread_intent enum value."""
    mapping = {
        "DELAY": "REPORT_DELAY",
        "BREAKDOWN": "REPORT_DELAY",
        "TRAFFIC": "REPORT_DELAY",
        "WEATHER": "REPORT_DELAY",
        "EARLY_ARRIVAL": "EARLY_ARRIVAL",
        "DOCK_UNAVAILABLE": "REPORT_DELAY",
        "UNKNOWN": "UNKNOWN",
    }
    return mapping.get(issue_type, "UNKNOWN")


# ---------------------------------------------------------------------------
# Tool: Record Driver Issue
# ---------------------------------------------------------------------------


@tool
def record_driver_issue(
    shipment_id: str,
    driver_id: str,
    vehicle_id: str,
    issue_type: str,
    issue_description: str,
    estimated_arrival: str,
    delay_minutes: int,
    destination_facility_id: str,
    severity: str,
    session_id: str,
    constraints: Optional[str] = None,
    recommended_action: Optional[str] = None,
) -> dict:
    """
    Records a driver-reported issue by inserting records into chat_threads
    and driver_exceptions tables. Call this tool ONLY after all required
    information has been collected from the driver.

    Args:
        shipment_id: The shipment ID affected (e.g. SHP1014).
        driver_id: The reporting driver's ID (e.g. DRV014).
        vehicle_id: The vehicle ID (e.g. VEH014).
        issue_type: One of DELAY, BREAKDOWN, TRAFFIC, WEATHER, EARLY_ARRIVAL, DOCK_UNAVAILABLE, UNKNOWN.
        issue_description: Brief plain-English summary of the problem.
        estimated_arrival: Driver's declared ETA in ISO-8601 format (e.g. 2026-08-04T11:25:00+05:30).
        delay_minutes: How many minutes late versus the original plan.
        destination_facility_id: The destination facility ID (e.g. FAC-JAI-01).
        severity: One of LOW, MEDIUM, HIGH, CRITICAL.
        session_id: The current conversation session ID (used as thread_id).
        constraints: Optional constraints (e.g. must leave by 1:30 PM, reefer required).
        recommended_action: Optional suggested next step for operations.

    Returns:
        A dict with status, thread_id, and exception_id confirming the records were created.
    """
    now = _now_iso()

    # --- Deduplication check ---
    dedupe_key = _build_dedupe_key(driver_id, shipment_id, now)
    existing = check_duplicate_exception(dedupe_key)
    if existing:
        logger.info(f"[tool:record_driver_issue] Duplicate detected: {dedupe_key}")
        return {
            "status": "duplicate",
            "message": "This issue has already been recorded.",
            "existing_exception_id": existing.get("exception_id"),
            "thread_id": existing.get("thread_id"),
        }

    # --- Insert chat_thread ---
    thread_id = session_id
    thread_intent = _map_issue_to_intent(issue_type)

    thread_data = {
        "thread_id": thread_id,
        "driver_id": driver_id,
        "shipment_id": shipment_id,
        "opened_at": now,
        "closed_at": None,
        "thread_status": "OPEN",
        "thread_intent": thread_intent,
    }

    try:
        create_chat_thread(thread_data)
        logger.info(f"[tool:record_driver_issue] Created chat_thread: {thread_id}")
    except Exception as e:
        logger.warning(f"[tool:record_driver_issue] chat_thread insert failed (may already exist): {e}")

    # --- Insert driver_exception ---
    exception_id = _generate_exception_id()

    full_description = issue_description
    if constraints:
        full_description += f" | Constraints: {constraints}"
    if recommended_action:
        full_description += f" | Recommended: {recommended_action}"

    exception_data = {
        "exception_id": exception_id,
        "shipment_id": shipment_id,
        "driver_id": driver_id,
        "thread_id": thread_id,
        "exception_type": issue_type,
        "reported_at": now,
        "reported_delay_min": max(delay_minutes, 0),
        "declared_eta_ts": estimated_arrival,
        "earliest_acceptable_ts": estimated_arrival,
        "latest_acceptable_ts": None,
        "severity_code": severity,
        "exception_status": "OPEN",
        "description": full_description,
        "dedupe_key": dedupe_key,
    }

    try:
        create_exception(exception_data)
        logger.info(f"[tool:record_driver_issue] Created driver_exception: {exception_id}")
    except Exception as e:
        error_msg = f"Failed to insert driver_exception: {e}"
        logger.error(f"[tool:record_driver_issue] {error_msg}")
        return {
            "status": "error",
            "message": error_msg,
            "thread_id": thread_id,
            "exception_id": None,
        }

    return {
        "status": "success",
        "message": "Issue recorded successfully. Operations team has been notified.",
        "thread_id": thread_id,
        "exception_id": exception_id,
        "severity": severity,
        "issue_type": issue_type,
    }
