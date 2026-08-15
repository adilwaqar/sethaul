"""
SetuHaul Database Client — Supabase Operations Layer

Provides reusable, typed functions for all database operations needed by:
- Agent tools (scheduling, exception handling, slot queries)
- API routes (driver status, appointment management)
- Background jobs (no-show detection, notification triggers)

All functions use the Supabase Python client and return dicts or lists of dicts.
Errors are raised as exceptions; callers decide how to handle them.
"""

import os
import logging
from typing import Optional
from datetime import datetime

from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

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
# Generic Helpers
# ---------------------------------------------------------------------------


def _query_table(
    table: str,
    columns: str = "*",
    filters: Optional[dict] = None,
    order_by: Optional[str] = None,
    order_desc: bool = False,
    limit: Optional[int] = None,
) -> list[dict]:
    """
    Generic SELECT query builder.

    Args:
        table: Table name.
        columns: Comma-separated column names or "*".
        filters: Dict of {column: value} for equality filters.
        order_by: Column to sort by.
        order_desc: Sort descending if True.
        limit: Max rows to return.

    Returns:
        List of row dicts.
    """
    query = get_client().table(table).select(columns)

    if filters:
        for col, val in filters.items():
            query = query.eq(col, val)

    if order_by:
        query = query.order(order_by, desc=order_desc)

    if limit:
        query = query.limit(limit)

    response = query.execute()
    return response.data


def _insert_row(table: str, data: dict) -> dict:
    """Insert a single row and return the inserted record."""
    response = get_client().table(table).insert(data).execute()
    return response.data[0] if response.data else {}


def _update_rows(table: str, data: dict, filters: dict) -> list[dict]:
    """Update rows matching filters and return updated records."""
    query = get_client().table(table).update(data)
    for col, val in filters.items():
        query = query.eq(col, val)
    response = query.execute()
    return response.data


def _delete_rows(table: str, filters: dict) -> list[dict]:
    """Delete rows matching filters and return deleted records."""
    query = get_client().table(table).delete()
    for col, val in filters.items():
        query = query.eq(col, val)
    response = query.execute()
    return response.data


# ---------------------------------------------------------------------------
# Shipments
# ---------------------------------------------------------------------------


def get_shipment(shipment_id: str) -> Optional[dict]:
    """Fetch a single shipment by ID."""
    rows = _query_table("shipments", filters={"shipment_id": shipment_id}, limit=1)
    return rows[0] if rows else None


def get_shipments_by_driver(driver_id: str) -> list[dict]:
    """Fetch all shipments assigned to a driver, ordered by planned departure."""
    return _query_table(
        "shipments",
        filters={"driver_id": driver_id},
        order_by="planned_departure_ts",
        order_desc=True
    )


def get_shipments_by_facility(
    facility_id: str, status: Optional[str] = None
) -> list[dict]:
    """Fetch shipments headed to a facility, optionally filtered by status."""
    filters: dict = {"destination_facility_id": facility_id}
    if status:
        filters["current_status"] = status
    return _query_table("shipments", filters=filters, order_by="latest_eta_ts")


def get_active_inbound_shipments(facility_id: str) -> list[dict]:
    """Fetch shipments that are IN_TRANSIT or WAITING for a facility."""
    client = get_client()
    response = (
        client.table("shipments")
        .select("*")
        .eq("destination_facility_id", facility_id)
        .in_("current_status", ["IN_TRANSIT", "AT_GATE", "WAITING", "IN_DOCK"])
        .order("latest_eta_ts")
        .execute()
    )
    return response.data


def update_shipment_status(shipment_id: str, status: str) -> list[dict]:
    """Update the current_status and updated_at for a shipment."""
    return _update_rows(
        "shipments",
        {"current_status": status, "updated_at": _now_iso()},
        {"shipment_id": shipment_id},
    )


def update_shipment_eta(shipment_id: str, eta: str) -> list[dict]:
    """Update the latest_eta_ts for a shipment."""
    return _update_rows(
        "shipments",
        {"latest_eta_ts": eta, "updated_at": _now_iso()},
        {"shipment_id": shipment_id},
    )


# ---------------------------------------------------------------------------
# Drivers
# ---------------------------------------------------------------------------


def get_driver(driver_id: str) -> Optional[dict]:
    """Fetch a driver by ID."""
    rows = _query_table("drivers", filters={"driver_id": driver_id}, limit=1)
    return rows[0] if rows else None


def get_driver_by_phone(phone: str) -> Optional[dict]:
    """Fetch a driver by phone number."""
    rows = _query_table("drivers", filters={"phone": phone}, limit=1)
    return rows[0] if rows else None


def get_drivers_by_carrier(carrier_id: str) -> list[dict]:
    """Fetch all active drivers for a carrier."""
    return _query_table(
        "drivers", filters={"carrier_id": carrier_id, "driver_status": "ACTIVE"}
    )


# ---------------------------------------------------------------------------
# Vehicles
# ---------------------------------------------------------------------------


def get_vehicle(vehicle_id: str) -> Optional[dict]:
    """Fetch a vehicle by ID."""
    rows = _query_table("vehicles", filters={"vehicle_id": vehicle_id}, limit=1)
    return rows[0] if rows else None


def get_vehicle_by_registration(registration: str) -> Optional[dict]:
    """Fetch a vehicle by registration number."""
    rows = _query_table(
        "vehicles", filters={"registration_number": registration}, limit=1
    )
    return rows[0] if rows else None


# ---------------------------------------------------------------------------
# Facilities & Docks
# ---------------------------------------------------------------------------


def get_facility(facility_id: str) -> Optional[dict]:
    """Fetch a facility by ID."""
    rows = _query_table("facilities", filters={"facility_id": facility_id}, limit=1)
    return rows[0] if rows else None


def get_all_facilities() -> list[dict]:
    """Fetch all active facilities."""
    return _query_table("facilities", filters={"active_flag": 1})


def get_docks_by_facility(
    facility_id: str, dock_type: Optional[str] = None
) -> list[dict]:
    """Fetch docks for a facility, optionally filtered by type."""
    filters: dict = {"facility_id": facility_id}
    if dock_type:
        filters["dock_type"] = dock_type
    return _query_table("docks", filters=filters)


def get_facility_rules(facility_id: str) -> list[dict]:
    """Fetch active rules for a facility."""
    return _query_table(
        "facility_rules", filters={"facility_id": facility_id, "active_flag": 1}
    )


def get_facility_contacts(facility_id: str) -> list[dict]:
    """Fetch active contacts for a facility."""
    return _query_table(
        "facility_contacts", filters={"facility_id": facility_id, "active_flag": 1}
    )


# ---------------------------------------------------------------------------
# Appointment Slots
# ---------------------------------------------------------------------------


def get_available_slots(
    facility_id: str,
    after_ts: str,
    dock_type: Optional[str] = None,
) -> list[dict]:
    """
    Fetch OPEN slots at a facility starting after a given timestamp.
    Optionally filter by dock type via join with docks table.
    """
    client = get_client()
    query = (
        client.table("appointment_slots")
        .select("*, docks(dock_type, supports_refrigerated, max_vehicle_weight_kg)")
        .eq("facility_id", facility_id)
        .eq("slot_status", "OPEN")
        .gte("slot_start_ts", after_ts)
        .order("slot_start_ts")
    )
    response = query.execute()
    rows = response.data

    # Filter by dock_type if specified (post-filter on joined data)
    if dock_type and rows:
        rows = [r for r in rows if r.get("docks", {}).get("dock_type") == dock_type]

    return rows


def get_slot(slot_id: str) -> Optional[dict]:
    """Fetch a single slot by ID."""
    rows = _query_table("appointment_slots", filters={"slot_id": slot_id}, limit=1)
    return rows[0] if rows else None


def block_slot(slot_id: str, reason: str) -> list[dict]:
    """Block a slot with a reason."""
    return _update_rows(
        "appointment_slots",
        {"slot_status": "BLOCKED", "block_reason": reason},
        {"slot_id": slot_id},
    )


# ---------------------------------------------------------------------------
# Appointments
# ---------------------------------------------------------------------------


def get_current_appointment(shipment_id: str) -> Optional[dict]:
    """Fetch the current active appointment for a shipment."""
    client = get_client()
    response = (
        client.table("appointments")
        .select("*")
        .eq("shipment_id", shipment_id)
        .eq("is_current", 1)
        .in_(
            "appointment_status",
            ["PENDING_CONFIRMATION", "CONFIRMED", "IN_PROGRESS"],
        )
        .limit(1)
        .execute()
    )
    return response.data[0] if response.data else None


def get_appointments_by_shipment(shipment_id: str) -> list[dict]:
    """Fetch all appointments (including history) for a shipment."""
    return _query_table(
        "appointments",
        filters={"shipment_id": shipment_id},
        order_by="booked_at",
        order_desc=True,
    )


def create_appointment(data: dict) -> dict:
    """
    Create a new appointment.

    Required fields: appointment_id, shipment_id, slot_id,
    appointment_status, booking_source, booked_at, updated_at.
    """
    return _insert_row("appointments", data)


def update_appointment_status(
    appointment_id: str, status: str, extra: Optional[dict] = None
) -> list[dict]:
    """Update an appointment's status with optional extra fields."""
    update_data = {"appointment_status": status, "updated_at": _now_iso()}
    if extra:
        update_data.update(extra)
    return _update_rows(
        "appointments", update_data, {"appointment_id": appointment_id}
    )


def cancel_appointment(appointment_id: str, reason: str) -> list[dict]:
    """Cancel an appointment with a reason and mark it non-current."""
    return _update_rows(
        "appointments",
        {
            "appointment_status": "CANCELLED",
            "is_current": 0,
            "cancelled_at": _now_iso(),
            "cancellation_reason": reason,
            "updated_at": _now_iso(),
        },
        {"appointment_id": appointment_id},
    )


# ---------------------------------------------------------------------------
# ETA Updates
# ---------------------------------------------------------------------------


def get_latest_eta(shipment_id: str) -> Optional[dict]:
    """Fetch the most recent ETA update for a shipment."""
    rows = _query_table(
        "eta_updates",
        filters={"shipment_id": shipment_id},
        order_by="created_at",
        order_desc=True,
        limit=1,
    )
    return rows[0] if rows else None


def get_eta_history(shipment_id: str) -> list[dict]:
    """Fetch all ETA updates for a shipment, newest first."""
    return _query_table(
        "eta_updates",
        filters={"shipment_id": shipment_id},
        order_by="created_at",
        order_desc=True,
    )


def create_eta_update(data: dict) -> dict:
    """
    Insert a new ETA update.

    Required fields: eta_update_id, shipment_id, source_type,
    declared_eta_ts, created_at.
    """
    return _insert_row("eta_updates", data)


# ---------------------------------------------------------------------------
# Dock Status Events
# ---------------------------------------------------------------------------


def get_active_dock_events(facility_id: str) -> list[dict]:
    """Fetch current dock events (breakdown/maintenance) for a facility's docks."""
    client = get_client()
    response = (
        client.table("dock_status_events")
        .select("*, docks(facility_id, dock_code, dock_type)")
        .is_("event_end_ts", "null")
        .execute()
    )
    # Post-filter by facility
    rows = response.data or []
    return [
        r
        for r in rows
        if r.get("docks", {}).get("facility_id") == facility_id
    ]


def get_dock_events_in_range(dock_id: str, start_ts: str, end_ts: str) -> list[dict]:
    """Fetch dock events overlapping a time range."""
    client = get_client()
    response = (
        client.table("dock_status_events")
        .select("*")
        .eq("dock_id", dock_id)
        .lte("event_start_ts", end_ts)
        .or_(f"event_end_ts.gte.{start_ts},event_end_ts.is.null")
        .execute()
    )
    return response.data


def create_dock_event(data: dict) -> dict:
    """Insert a new dock status event."""
    return _insert_row("dock_status_events", data)


# ---------------------------------------------------------------------------
# Facility Check-ins
# ---------------------------------------------------------------------------


def get_checkin(shipment_id: str) -> Optional[dict]:
    """Fetch the facility check-in record for a shipment."""
    rows = _query_table(
        "facility_checkins", filters={"shipment_id": shipment_id}, limit=1
    )
    return rows[0] if rows else None


def get_facility_queue(facility_id: str) -> list[dict]:
    """Fetch trucks currently waiting at a facility, ordered by queue position."""
    client = get_client()
    response = (
        client.table("facility_checkins")
        .select("*, shipments(driver_id, vehicle_id, priority_code, required_dock_type, expected_unload_min)")
        .eq("facility_id", facility_id)
        .in_(
            "queue_state",
            [
                "WAITING_EARLY",
                "WAITING_LATE",
                "WAITING_DOCK_UNAVAILABLE",
                "CALLED_TO_DOCK",
            ],
        )
        .order("queue_position")
        .execute()
    )
    return response.data


def create_checkin(data: dict) -> dict:
    """Insert a new facility check-in record."""
    return _insert_row("facility_checkins", data)


def update_checkin(shipment_id: str, data: dict) -> list[dict]:
    """Update a check-in record for a shipment."""
    data["updated_at"] = _now_iso()
    return _update_rows("facility_checkins", data, {"shipment_id": shipment_id})


# ---------------------------------------------------------------------------
# Chat Threads & Messages
# ---------------------------------------------------------------------------


def get_chat_thread(thread_id: str) -> Optional[dict]:
    """Fetch a chat thread by ID."""
    rows = _query_table("chat_threads", filters={"thread_id": thread_id}, limit=1)
    return rows[0] if rows else None


def get_open_threads_for_driver(driver_id: str) -> list[dict]:
    """Fetch all non-closed threads for a driver."""
    client = get_client()
    response = (
        client.table("chat_threads")
        .select("*")
        .eq("driver_id", driver_id)
        .neq("thread_status", "CLOSED")
        .order("opened_at", desc=True)
        .execute()
    )
    return response.data


def create_chat_thread(data: dict) -> dict:
    """
    Create a new chat thread.

    Required fields: thread_id, driver_id, opened_at, thread_status, thread_intent.
    """
    return _insert_row("chat_threads", data)


def update_chat_thread(thread_id: str, data: dict) -> list[dict]:
    """Update a chat thread (status, intent, closed_at, etc.)."""
    return _update_rows("chat_threads", data, {"thread_id": thread_id})


def get_thread_messages(thread_id: str) -> list[dict]:
    """Fetch all messages in a thread, ordered by timestamp."""
    return _query_table(
        "chat_messages", filters={"thread_id": thread_id}, order_by="message_ts"
    )


def create_chat_message(data: dict) -> dict:
    """
    Insert a new chat message.

    Required fields: chat_message_id, thread_id, sender_type,
    message_text, message_ts.
    """
    return _insert_row("chat_messages", data)


# ---------------------------------------------------------------------------
# Driver Exceptions
# ---------------------------------------------------------------------------


def get_exception(exception_id: str) -> Optional[dict]:
    """Fetch a driver exception by ID."""
    rows = _query_table(
        "driver_exceptions", filters={"exception_id": exception_id}, limit=1
    )
    return rows[0] if rows else None


def get_open_exceptions(facility_id: Optional[str] = None) -> list[dict]:
    """
    Fetch all open/active exceptions, optionally filtered by destination facility.
    Joins with shipments to get facility context.
    """
    client = get_client()
    query = (
        client.table("driver_exceptions")
        .select("*, shipments(destination_facility_id, priority_code, required_dock_type)")
        .in_(
            "exception_status",
            ["OPEN", "NEEDS_INFORMATION", "SLOT_OPTIONS_SHARED", "WAITING_CONFIRMATION"],
        )
        .order("reported_at", desc=True)
    )
    response = query.execute()
    rows = response.data or []

    if facility_id:
        rows = [
            r
            for r in rows
            if r.get("shipments", {}).get("destination_facility_id") == facility_id
        ]

    return rows


def get_exceptions_by_shipment(shipment_id: str) -> list[dict]:
    """Fetch all exceptions for a shipment."""
    return _query_table(
        "driver_exceptions",
        filters={"shipment_id": shipment_id},
        order_by="reported_at",
        order_desc=True,
    )


def create_exception(data: dict) -> dict:
    """
    Insert a new driver exception.

    Required fields: exception_id, driver_id, thread_id, exception_type,
    reported_at, severity_code, exception_status, description.
    """
    return _insert_row("driver_exceptions", data)


def update_exception(exception_id: str, data: dict) -> list[dict]:
    """Update an exception record."""
    return _update_rows("driver_exceptions", data, {"exception_id": exception_id})


def check_duplicate_exception(dedupe_key: str) -> Optional[dict]:
    """Check if an exception with the same dedupe_key already exists."""
    rows = _query_table(
        "driver_exceptions", filters={"dedupe_key": dedupe_key}, limit=1
    )
    return rows[0] if rows else None


# ---------------------------------------------------------------------------
# Operational Messages
# ---------------------------------------------------------------------------


def get_messages_for_shipment(shipment_id: str) -> list[dict]:
    """Fetch all operational messages for a shipment."""
    return _query_table(
        "operational_messages",
        filters={"shipment_id": shipment_id},
        order_by="sent_at",
        order_desc=True,
    )


def create_operational_message(data: dict) -> dict:
    """
    Insert a new operational message (email/SMS/WhatsApp notification).

    Required fields: operational_message_id, shipment_id, channel,
    sender_address, recipient_address, message_body, sent_at, delivery_status.
    """
    return _insert_row("operational_messages", data)


def update_message_status(
    message_id: str, status: str, extra: Optional[dict] = None
) -> list[dict]:
    """Update delivery status of an operational message."""
    update_data = {"delivery_status": status}
    if extra:
        update_data.update(extra)
    return _update_rows(
        "operational_messages", update_data, {"operational_message_id": message_id}
    )


# ---------------------------------------------------------------------------
# Carriers
# ---------------------------------------------------------------------------


def get_carrier(carrier_id: str) -> Optional[dict]:
    """Fetch a carrier by ID."""
    rows = _query_table("carriers", filters={"carrier_id": carrier_id}, limit=1)
    return rows[0] if rows else None


def get_all_carriers() -> list[dict]:
    """Fetch all active carriers."""
    return _query_table("carriers", filters={"active_flag": 1})


# ---------------------------------------------------------------------------
# Views (RPC calls for complex queries)
# ---------------------------------------------------------------------------


def get_inbound_operational_state(facility_id: str) -> list[dict]:
    """
    Query the v_inbound_operational_state view.
    Falls back to RPC or direct view query depending on Supabase setup.
    """
    client = get_client()
    response = (
        client.table("v_inbound_operational_state")
        .select("*")
        .eq("destination_facility_id", facility_id)
        .order("effective_eta_ts")
        .execute()
    )
    return response.data


def get_slot_availability(
    facility_id: str,
    dock_type: Optional[str] = None,
    after_ts: Optional[str] = None,
    status: Optional[str] = None,
) -> list[dict]:
    """
    Query the v_slot_availability view with optional filters.

    Args:
        facility_id: Target facility.
        dock_type: Filter by STANDARD, REEFER, or HEAVY.
        after_ts: Only slots starting at or after this time.
        status: Filter by AVAILABLE, OCCUPIED, BLOCKED, or CLOSED.
    """
    client = get_client()
    query = (
        client.table("v_slot_availability")
        .select("*")
        .eq("facility_id", facility_id)
    )

    if dock_type:
        query = query.eq("dock_type", dock_type)
    if after_ts:
        query = query.gte("slot_start_ts", after_ts)
    if status:
        query = query.eq("availability_status", status)

    response = query.order("slot_start_ts").execute()
    return response.data


def get_latest_eta_view(shipment_id: str) -> Optional[dict]:
    """Query the v_latest_eta view for a single shipment."""
    client = get_client()
    response = (
        client.table("v_latest_eta")
        .select("*")
        .eq("shipment_id", shipment_id)
        .limit(1)
        .execute()
    )
    return response.data[0] if response.data else None


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    """Current timestamp in ISO-8601 format with Asia/Kolkata offset."""
    now = datetime.now()
    return now.strftime("%Y-%m-%dT%H:%M:%S+05:30")
