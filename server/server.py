"""
SetuHaul Driver Chat — FastAPI Server

Production-ready HTTP server that provides:
- Driver authentication by phone number
- Chat invocation with session management
- Session resumption (driver sees last open session on return)

Runs on port 8000. Compatible with Replit deployment.
"""

import os
import sys
import uuid
import logging
from pathlib import Path
from typing import Optional
from datetime import datetime, timedelta
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from dotenv import load_dotenv

# Ensure the server directory is in the Python path
sys.path.insert(0, str(Path(__file__).resolve().parent))

load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent / ".env")

from db import (
    get_driver_by_phone,
    get_driver,
    get_open_threads_for_driver,
    get_thread_messages,
    get_chat_thread,
    get_exceptions_by_shipment,
    get_shipments_by_driver,
    create_chat_message,
    get_all_facilities,
    get_active_inbound_shipments,
    get_open_exceptions,
    get_exception,
    get_shipment,
    get_available_slots,
    get_slot_availability,
    get_current_appointment,
    get_latest_eta,
    update_exception,
    update_appointment_status,
    cancel_appointment,
    create_appointment,
    update_shipment_eta,
    get_docks_by_facility,
    get_facility,
    get_facility_rules,
    get_vehicle,
    get_all_carriers,
    create_eta_update,
)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("sethaul.server")


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown hooks."""
    logger.info("SetuHaul FastAPI server starting...")
    yield
    logger.info("SetuHaul FastAPI server shutting down.")


# ---------------------------------------------------------------------------
# App Setup
# ---------------------------------------------------------------------------

app = FastAPI(
    title="SetuHaul Driver Chat API",
    description="Backend API for driver issue reporting and session management.",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS — allow Vercel frontend and local dev
ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://localhost:5173",
    "https://sethaul.vercel.app",
]

# In production, set CORS_ORIGINS env var to your Vercel domain
cors_origins_env = os.environ.get("CORS_ORIGINS", "")
if cors_origins_env:
    ALLOWED_ORIGINS.extend(cors_origins_env.split(","))

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://sethaul.vercel.app"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)


# ---------------------------------------------------------------------------
# Request / Response Models
# ---------------------------------------------------------------------------

class DriverLoginRequest(BaseModel):
    phone: str = Field(..., description="Driver's phone number (e.g. +91-9000010014)")


class DriverLoginResponse(BaseModel):
    driver_id: str
    driver_name: str
    phone: str
    carrier_id: str
    home_base_city: Optional[str] = None
    active_sessions: Optional[list[dict]] = None


class ChatRequest(BaseModel):
    prompt: str = Field(..., min_length=1, description="Driver's message text")
    session_id: str = Field(..., min_length=1, description="Session ID for conversation continuity")
    driver_id: str = Field(..., min_length=1, description="Authenticated driver ID")
    shipment_id: str = Field(..., min_length=1, description="Selected shipment ID for this session")


class ChatResponse(BaseModel):
    result: str
    session_id: str
    error: Optional[str] = None


class SessionInfoResponse(BaseModel):
    session_id: str
    driver_id: str
    shipment_id: Optional[str] = None
    thread_status: str
    thread_intent: str
    opened_at: str
    messages: list[dict] = []


class NewSessionResponse(BaseModel):
    session_id: str
    driver_id: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    """Current timestamp in ISO-8601 with +05:30 offset."""
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S+05:30")


def _generate_session_id() -> str:
    """Generate a unique session ID (>= 33 chars for AgentCore compat)."""
    return f"drv-{uuid.uuid4()}"


def _generate_message_id() -> str:
    """Generate a unique chat message ID."""
    short_id = uuid.uuid4().hex[:10].upper()
    return f"MSG-{short_id}"


def _persist_driver_message(session_id: str, driver_id: str, text: str) -> None:
    """Store the driver's message in chat_messages table."""
    try:
        create_chat_message({
            "chat_message_id": _generate_message_id(),
            "thread_id": session_id,
            "sender_type": "DRIVER",
            "sender_reference": driver_id,
            "message_text": text,
            "message_ts": _now_iso(),
            "is_duplicate": 0,
            "requires_human_review": 0,
        })
    except Exception as e:
        logger.warning(f"[chat] Failed to persist driver message: {e}")


def _persist_agent_message(session_id: str, text: str) -> None:
    """Store the agent's response in chat_messages table."""
    try:
        create_chat_message({
            "chat_message_id": _generate_message_id(),
            "thread_id": session_id,
            "sender_type": "AGENT",
            "sender_reference": "agent",
            "message_text": text,
            "message_ts": _now_iso(),
            "is_duplicate": 0,
            "requires_human_review": 0,
        })
    except Exception as e:
        logger.warning(f"[chat] Failed to persist agent message: {e}")


def _ensure_chat_thread(session_id: str, driver_id: str, shipment_id: str) -> None:
    """Create a chat_thread record if one doesn't exist for this session."""
    from db import create_chat_thread

    existing = get_chat_thread(session_id)
    if existing:
        # Update shipment_id if it was missing
        if not existing.get("shipment_id") and shipment_id:
            from db import _update_rows
            _update_rows("chat_threads", {"shipment_id": shipment_id}, {"thread_id": session_id})
        return  # Already exists

    try:
        create_chat_thread({
            "thread_id": session_id,
            "driver_id": driver_id,
            "shipment_id": shipment_id,
            "opened_at": _now_iso(),
            "closed_at": None,
            "thread_status": "OPEN",
            "thread_intent": "UNKNOWN",
        })
        logger.info(f"[chat] Created chat_thread for session {session_id}, shipment {shipment_id}")
    except Exception as e:
        logger.warning(f"[chat] Failed to create chat_thread (may already exist): {e}")


def _build_driver_context(driver_id: str, selected_shipment_id: str = "") -> str:
    """
    Build a context block with the driver's identity and active shipment details.
    Highlights the selected shipment so the agent focuses on it.
    """
    driver = get_driver(driver_id)
    if not driver:
        return ""

    # Current date/time for proper "today"/"tomorrow" resolution
    now = datetime.now()
    today_str = now.strftime("%Y-%m-%d")
    tomorrow_str = (now + timedelta(days=1)).strftime("%Y-%m-%d")
    current_time_str = now.strftime("%H:%M")

    # Get driver's active shipments (IN_TRANSIT, ASSIGNED, PLANNED, WAITING, AT_GATE)
    from db import get_client as _gc
    client = _gc()
    shipments_resp = (
        client.table("shipments")
        .select(
            "shipment_id, order_reference, carrier_id, vehicle_id, "
            "origin_name, origin_city, destination_facility_id, customer_name, "
            "product_category, load_weight_kg, required_dock_type, "
            "temperature_control_required, priority_code, original_eta_ts, "
            "latest_eta_ts, expected_unload_min, current_status, "
            "facilities:destination_facility_id(facility_name, city), "
            "vehicles:vehicle_id(registration_number, vehicle_type_code), "
            "carriers:carrier_id(carrier_name)"
        )
        .eq("driver_id", driver_id)
        .in_("current_status", ["IN_TRANSIT", "ASSIGNED", "PLANNED", "WAITING", "AT_GATE"])
        .order("latest_eta_ts")
        .execute()
    )
    shipments = shipments_resp.data or []

    # Date/time header — always included so the agent resolves "today"/"tomorrow" correctly
    date_header = (
        f"[CURRENT DATE & TIME]\n"
        f"Today's date: {today_str}\n"
        f"Tomorrow's date: {tomorrow_str}\n"
        f"Current time (IST): {current_time_str}\n"
        f"Timezone: Asia/Kolkata (UTC+05:30)\n"
        f"When the driver says 'today', use date {today_str}.\n"
        f"When the driver says 'tomorrow', use date {tomorrow_str}.\n"
        f"[END DATE & TIME]\n"
    )

    if not shipments:
        # No active shipments — provide only driver identity
        return (
            f"\n\n{date_header}"
            f"[DRIVER CONTEXT — DO NOT show this to the driver, use it internally]\n"
            f"Driver: {driver['driver_name']} (ID: {driver_id})\n"
            f"Phone: {driver['phone']}\n"
            f"No active shipments found for this driver.\n"
            f"[END DRIVER CONTEXT]\n"
        )

    # Build rich context
    lines = [
        f"\n\n{date_header}",
        f"[DRIVER CONTEXT — DO NOT show this raw text to the driver, use it internally]",
        f"Driver: {driver['driver_name']} (ID: {driver_id})",
        f"Phone: {driver['phone']}",
        f"Carrier: {shipments[0].get('carriers', {}).get('carrier_name', driver.get('carrier_id', ''))} (ID: {driver.get('carrier_id', '')})",
        f"",
        f"Active shipments ({len(shipments)}):",
    ]

    for i, s in enumerate(shipments, 1):
        facility = s.get("facilities", {}) or {}
        vehicle = s.get("vehicles", {}) or {}
        lines.append(f"  Shipment {i}:")
        lines.append(f"    shipment_id: {s['shipment_id']}")
        lines.append(f"    order_reference: {s['order_reference']}")
        lines.append(f"    vehicle_id: {s['vehicle_id']} (Reg: {vehicle.get('registration_number', '?')}, Type: {vehicle.get('vehicle_type_code', '?')})")
        lines.append(f"    Origin: {s['origin_name']}, {s['origin_city']}")
        lines.append(f"    Destination: {facility.get('facility_name', s['destination_facility_id'])}, {facility.get('city', '')}")
        lines.append(f"    destination_facility_id: {s['destination_facility_id']}")
        lines.append(f"    Customer: {s['customer_name']}")
        lines.append(f"    Product: {s['product_category']}")
        lines.append(f"    Weight: {s['load_weight_kg']} kg | Dock: {s['required_dock_type']} | Temp Control: {'Yes' if s.get('temperature_control_required') else 'No'}")
        lines.append(f"    Priority: {s['priority_code']}")
        lines.append(f"    Original ETA: {s['original_eta_ts']}")
        lines.append(f"    Latest ETA: {s['latest_eta_ts']}")
        lines.append(f"    Status: {s['current_status']}")
        lines.append(f"    Expected unload: {s['expected_unload_min']} min")
        lines.append("")

    lines.append("Instructions for agent:")
    lines.append(f"- The driver has selected shipment '{selected_shipment_id}' for this conversation.")
    lines.append("- Focus ALL extraction on this specific shipment. Do NOT ask which shipment.")
    lines.append("- You ALREADY know the driver_id, vehicle_id, shipment_id, and destination_facility_id from above.")
    lines.append("- Do NOT ask the driver for these IDs. Use them directly.")
    lines.append("- If the driver mentions a DIFFERENT shipment that doesn't match the selected one, confirm: 'You selected [shipment X] for this chat. Are you asking about a different shipment?'")
    lines.append("- Ask only for MISSING info: the issue, estimated arrival time, and any constraints.")
    lines.append("- Do NOT ask for date or day — assume today unless driver says otherwise.")
    lines.append("[END DRIVER CONTEXT]")

    return "\n".join(lines)


async def _invoke_agent(prompt: str, session_id: str) -> dict:
    """
    Invoke the agent running on localhost:8080 with prompt and session_id.
    """
    from agent_invoker import invoke_agent
    return await invoke_agent(prompt=prompt, session_id=session_id)


# ---------------------------------------------------------------------------
# Routes: Health
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------

@app.post("/auth/login", response_model=DriverLoginResponse)
async def driver_login(body: DriverLoginRequest):
    """
    Authenticate a driver by phone number.

    Returns driver profile and their last open session (if any) so the
    frontend can resume the conversation.
    """
    phone = body.phone.strip()

    # Look up driver by phone
    driver = get_driver_by_phone(phone)
    if not driver:
        raise HTTPException(
            status_code=404,
            detail=f"No driver found with phone number: {phone}",
        )

    if driver.get("driver_status") != "ACTIVE":
        raise HTTPException(
            status_code=403,
            detail="Driver account is not active. Contact dispatch.",
        )

    driver_id = driver["driver_id"]

    # Check for an existing open session (thread)
    active_sessions = None
    open_threads = get_open_threads_for_driver(driver_id)
    if open_threads and len(open_threads):
        # Return the most recent open thread as the active session
        active_sessions = [ {
            "session_id": thread["thread_id"],
            "shipment_id": thread.get("shipment_id"),
            "thread_status": thread["thread_status"],
            "thread_intent": thread["thread_intent"],
            "opened_at": thread["opened_at"]
        } for thread in open_threads]

    logger.info(f"[auth] Driver {driver_id} logged in. Active session: {active_sessions is not None}")

    return DriverLoginResponse(
        driver_id=driver["driver_id"],
        driver_name=driver["driver_name"],
        phone=driver["phone"],
        carrier_id=driver["carrier_id"],
        home_base_city=driver.get("home_base_city"),
        active_sessions=active_sessions,
    )


# ---------------------------------------------------------------------------
# Routes: Session Management
# ---------------------------------------------------------------------------

@app.post("/sessions/new", response_model=NewSessionResponse)
async def create_new_session(driver_id: str = Query(..., description="Driver ID")):
    """Create a new chat session for a driver."""
    # Validate driver exists
    driver = get_driver(driver_id)
    if not driver:
        raise HTTPException(status_code=404, detail="Driver not found.")

    session_id = _generate_session_id()

    logger.info(f"[session] New session {session_id} for driver {driver_id}")

    return NewSessionResponse(session_id=session_id, driver_id=driver_id)


@app.get("/sessions/{session_id}", response_model=SessionInfoResponse)
async def get_session(session_id: str):
    """
    Get session details and message history.
    Returns messages only if the session/thread is still open (not CLOSED/RESOLVED).
    Used when a driver resumes a previous session.
    """
    thread = get_chat_thread(session_id)
    if not thread:
        raise HTTPException(status_code=404, detail="Session not found.")

    messages = get_thread_messages(session_id)

    return SessionInfoResponse(
        session_id=thread["thread_id"],
        driver_id=thread["driver_id"],
        shipment_id=thread.get("shipment_id"),
        thread_status=thread["thread_status"],
        thread_intent=thread["thread_intent"],
        opened_at=thread["opened_at"],
        messages=messages,
    )


@app.get("/sessions/driver/{driver_id}")
async def get_driver_sessions(driver_id: str):
    """Get all open sessions for a driver."""
    threads = get_open_threads_for_driver(driver_id)
    return {"driver_id": driver_id, "sessions": threads}


# ---------------------------------------------------------------------------
# Routes: Chat
# ---------------------------------------------------------------------------

@app.post("/chat", response_model=ChatResponse)
async def chat(body: ChatRequest):
    """
    Send a message to the agent and get a response.

    Flow:
    1. Ensure chat_thread exists for this session (creates on first message)
    2. Persist the driver's message in chat_messages
    3. Build driver context (shipments, vehicle, facility details)
    4. Invoke agent with enriched prompt (user message + context)
    5. Persist the agent's response in chat_messages
    6. Return the response to the client
    """
    try:
        # 1. Create chat_thread on first message of this session
        _ensure_chat_thread(session_id=body.session_id, driver_id=body.driver_id, shipment_id=body.shipment_id)

        # 2. Store driver message
        _persist_driver_message(
            session_id=body.session_id,
            driver_id=body.driver_id,
            text=body.prompt,
        )

        # 3. Build context with driver's shipment details
        driver_context = _build_driver_context(body.driver_id, body.shipment_id)
        print(f"driver_context: {driver_context}")

        # 4. Invoke agent with enriched prompt
        # The context is appended so the agent sees it but the driver's raw message is clear
        enriched_prompt = body.prompt + driver_context

        result = await _invoke_agent(
            prompt=enriched_prompt,
            session_id=body.session_id,
        )

        if "error" in result:
            return ChatResponse(
                result="",
                session_id=body.session_id,
                error=result["error"],
            )

        agent_response = result.get("result", "")

        # 5. Store agent response
        if agent_response:
            _persist_agent_message(
                session_id=body.session_id,
                text=agent_response,
            )

        return ChatResponse(
            result=agent_response,
            session_id=result.get("session_id", body.session_id),
        )

    except Exception as e:
        logger.error(f"[chat] Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Routes: Driver Info
# ---------------------------------------------------------------------------

@app.get("/drivers/{driver_id}/shipments")
async def get_driver_shipments(driver_id: str):
    """Get all shipments assigned to a driver."""
    driver = get_driver(driver_id)
    if not driver:
        raise HTTPException(status_code=404, detail="Driver not found.")

    shipments = get_shipments_by_driver(driver_id)
    return {"driver_id": driver_id, "shipments": shipments}


@app.get("/drivers/{driver_id}/exceptions")
async def get_driver_exceptions(driver_id: str):
    """Get all exception records for a driver's shipments."""
    shipments = get_shipments_by_driver(driver_id)
    all_exceptions = []
    for shipment in shipments:
        exceptions = get_exceptions_by_shipment(shipment["shipment_id"])
        all_exceptions.extend(exceptions)
    return {"driver_id": driver_id, "exceptions": all_exceptions}


# ---------------------------------------------------------------------------
# Routes: Driver — Shipment Context (for chat panel)
# ---------------------------------------------------------------------------

@app.get("/drivers/{driver_id}/context")
async def get_driver_context(driver_id: str):
    """
    Returns the driver's current and upcoming shipment info with:
    - Shipment details (facility, origin, status, ETAs)
    - Latest ETA update status (approved or pending)
    - Exception status (if driver requested an ETA change)
    - Appointment info

    Used by the chat screen's collapsible side panel.
    """
    from db import get_client as _gc

    driver = get_driver(driver_id)
    if not driver:
        raise HTTPException(status_code=404, detail="Driver not found.")

    client = _gc()

    # Get all non-cancelled shipments for this driver, ordered by ETA
    shipments_resp = (
        client.table("shipments")
        .select(
            "shipment_id, order_reference, origin_name, origin_city, "
            "destination_facility_id, customer_name, product_category, "
            "load_weight_kg, required_dock_type, priority_code, "
            "planned_departure_ts, actual_departure_ts, original_eta_ts, latest_eta_ts, current_status, expected_unload_min, "
            "facilities:destination_facility_id(facility_name, city), "
            "vehicles:vehicle_id(registration_number, vehicle_type_code)"
        )
        .eq("driver_id", driver_id)
        .neq("current_status", "CANCELLED")
        .order("latest_eta_ts", desc=True)
        .execute()
    )
    shipments = shipments_resp.data or []

    print(f"shipments_resp: {shipments_resp}")

    # For each shipment, get exception and ETA info
    enriched_shipments = []
    for s in shipments:
        sid = s["shipment_id"]

        # Latest exception for this shipment
        exc_resp = (
            client.table("driver_exceptions")
            .select("exception_id, exception_type, severity_code, exception_status, declared_eta_ts, reported_at, description")
            .eq("shipment_id", sid)
            .order("reported_at", desc=True)
            .limit(1)
            .execute()
        )
        latest_exception = exc_resp.data[0] if exc_resp.data else None

        # Latest ETA update
        eta_resp = (
            client.table("eta_updates")
            .select("eta_update_id, source_type, declared_eta_ts, confidence_code, delay_reason_code, note, created_at")
            .eq("shipment_id", sid)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        latest_eta_update = eta_resp.data[0] if eta_resp.data else None

        # Current appointment
        appt_resp = (
            client.table("appointments")
            .select("appointment_id, slot_id, appointment_status, booking_source, confirmed_at, appointment_slots:slot_id(slot_start_ts, slot_end_ts, dock_id)")
            .eq("shipment_id", sid)
            .eq("is_current", 1)
            .in_("appointment_status", ["PENDING_CONFIRMATION", "CONFIRMED", "IN_PROGRESS"])
            .limit(1)
            .execute()
        )
        current_appointment = appt_resp.data[0] if appt_resp.data else None

        # Determine ETA approval status for the driver's view
        eta_status = None
        if latest_exception and latest_exception["exception_status"] in ("OPEN", "NEEDS_INFORMATION", "WAITING_CONFIRMATION"):
            eta_status = "PENDING_APPROVAL"
        elif latest_exception and latest_exception["exception_status"] == "RESOLVED":
            eta_status = "APPROVED"
        elif latest_exception and latest_exception["exception_status"] == "ESCALATED":
            eta_status = "ESCALATED"

        enriched_shipments.append({
            **s,
            "latest_exception": latest_exception,
            "latest_eta_update": latest_eta_update,
            "current_appointment": current_appointment,
            "eta_approval_status": eta_status,
        })

    return {
        "driver_id": driver_id,
        "driver_name": driver["driver_name"],
        "shipments": enriched_shipments,
    }


# ---------------------------------------------------------------------------
# Routes: Admin — Shipment Status Update
# ---------------------------------------------------------------------------

class UpdateShipmentStatusRequest(BaseModel):
    status: str = Field(..., description="New status: PLANNED, ASSIGNED, IN_TRANSIT, AT_GATE, WAITING, IN_DOCK, COMPLETED, CANCELLED")
    notes: Optional[str] = Field(None, description="Optional notes for the status change")


@app.patch("/admin/shipments/{shipment_id}/status")
async def admin_update_shipment_status(shipment_id: str, body: UpdateShipmentStatusRequest):
    """
    Update a shipment's status and manage related facility_checkins records.

    Status transitions and their side effects:
    - AT_GATE: Creates facility_checkins record with gate_in_ts, determines arrival_state
    - WAITING: Sets yard_queue_enter_ts and queue_state
    - IN_DOCK: Sets dock_in_ts, unload_start_ts, queue_state=IN_DOCK
    - COMPLETED: Sets unload_end_ts, gate_out_ts, queue_state=COMPLETED
    - CANCELLED: Cancels any active appointment
    """
    from db import _insert_row, _update_rows, get_client as _gc

    VALID_STATUSES = ["PLANNED", "ASSIGNED", "IN_TRANSIT", "AT_GATE", "WAITING", "IN_DOCK", "COMPLETED", "CANCELLED"]
    if body.status not in VALID_STATUSES:
        raise HTTPException(status_code=400, detail=f"Invalid status. Must be one of: {VALID_STATUSES}")

    shipment = get_shipment(shipment_id)
    if not shipment:
        raise HTTPException(status_code=404, detail="Shipment not found.")

    now = _now_iso()
    facility_id = shipment["destination_facility_id"]
    original_eta = shipment.get("original_eta_ts", "")
    latest_eta = shipment.get("latest_eta_ts", "")

    # Update shipment status
    _update_rows("shipments", {"current_status": body.status, "updated_at": now}, {"shipment_id": shipment_id})

    # If transitioning to IN_TRANSIT, set actual_departure_ts
    if body.status == "IN_TRANSIT" and not shipment.get("actual_departure_ts"):
        _update_rows("shipments", {"actual_departure_ts": now}, {"shipment_id": shipment_id})

    # --- Facility check-in management ---
    client = _gc()

    if body.status == "AT_GATE":
        # Determine arrival state by comparing gate-in time to appointment slot
        arrival_state = _determine_arrival_state(shipment_id, now, client)

        # Check if checkin already exists
        existing = client.table("facility_checkins").select("checkin_id").eq("shipment_id", shipment_id).execute()
        if existing.data:
            # Update existing
            _update_rows("facility_checkins", {
                "gate_in_ts": now,
                "arrival_state": arrival_state,
                "queue_state": "NOT_QUEUED",
                "notes": body.notes,
                "updated_at": now,
            }, {"shipment_id": shipment_id})
        else:
            # Create new checkin
            checkin_id = f"CHK-{uuid.uuid4().hex[:8].upper()}"
            _insert_row("facility_checkins", {
                "checkin_id": checkin_id,
                "shipment_id": shipment_id,
                "facility_id": facility_id,
                "gate_in_ts": now,
                "yard_queue_enter_ts": None,
                "dock_in_ts": None,
                "unload_start_ts": None,
                "unload_end_ts": None,
                "gate_out_ts": None,
                "arrival_state": arrival_state,
                "queue_state": "NOT_QUEUED",
                "queue_position": None,
                "actual_dock_id": None,
                "notes": body.notes,
                "updated_at": now,
            })

    elif body.status == "WAITING":
        # Determine appropriate queue state
        existing = client.table("facility_checkins").select("checkin_id, arrival_state").eq("shipment_id", shipment_id).execute()
        if existing.data:
            arrival_state = existing.data[0].get("arrival_state", "LATE")
            queue_state = "WAITING_EARLY" if arrival_state == "EARLY" else "WAITING_LATE"
            _update_rows("facility_checkins", {
                "yard_queue_enter_ts": now,
                "queue_state": queue_state,
                "notes": body.notes,
                "updated_at": now,
            }, {"shipment_id": shipment_id})
        else:
            # Create checkin if it doesn't exist (direct to waiting without AT_GATE)
            checkin_id = f"CHK-{uuid.uuid4().hex[:8].upper()}"
            _insert_row("facility_checkins", {
                "checkin_id": checkin_id,
                "shipment_id": shipment_id,
                "facility_id": facility_id,
                "gate_in_ts": now,
                "yard_queue_enter_ts": now,
                "dock_in_ts": None,
                "unload_start_ts": None,
                "unload_end_ts": None,
                "gate_out_ts": None,
                "arrival_state": "LATE",
                "queue_state": "WAITING_LATE",
                "queue_position": None,
                "actual_dock_id": None,
                "notes": body.notes,
                "updated_at": now,
            })

    elif body.status == "IN_DOCK":
        # Get dock from current appointment
        appt = get_current_appointment(shipment_id)
        actual_dock_id = None
        if appt:
            slot = client.table("appointment_slots").select("dock_id").eq("slot_id", appt["slot_id"]).execute()
            if slot.data:
                actual_dock_id = slot.data[0]["dock_id"]

        existing = client.table("facility_checkins").select("checkin_id").eq("shipment_id", shipment_id).execute()
        if existing.data:
            _update_rows("facility_checkins", {
                "dock_in_ts": now,
                "unload_start_ts": now,
                "queue_state": "IN_DOCK",
                "actual_dock_id": actual_dock_id,
                "notes": body.notes,
                "updated_at": now,
            }, {"shipment_id": shipment_id})
        else:
            checkin_id = f"CHK-{uuid.uuid4().hex[:8].upper()}"
            _insert_row("facility_checkins", {
                "checkin_id": checkin_id,
                "shipment_id": shipment_id,
                "facility_id": facility_id,
                "gate_in_ts": now,
                "yard_queue_enter_ts": now,
                "dock_in_ts": now,
                "unload_start_ts": now,
                "unload_end_ts": None,
                "gate_out_ts": None,
                "arrival_state": "ON_TIME",
                "queue_state": "IN_DOCK",
                "queue_position": None,
                "actual_dock_id": actual_dock_id,
                "notes": body.notes,
                "updated_at": now,
            })

        # Update appointment to IN_PROGRESS
        if appt:
            _update_rows("appointments", {"appointment_status": "IN_PROGRESS", "updated_at": now}, {"appointment_id": appt["appointment_id"]})

    elif body.status == "COMPLETED":
        existing = client.table("facility_checkins").select("checkin_id").eq("shipment_id", shipment_id).execute()
        if existing.data:
            _update_rows("facility_checkins", {
                "unload_end_ts": now,
                "gate_out_ts": now,
                "queue_state": "COMPLETED",
                "notes": body.notes,
                "updated_at": now,
            }, {"shipment_id": shipment_id})

        # Mark appointment as COMPLETED
        appt = get_current_appointment(shipment_id)
        if appt:
            _update_rows("appointments", {"appointment_status": "COMPLETED", "updated_at": now}, {"appointment_id": appt["appointment_id"]})

        # Close all open threads for this shipment
        open_threads = client.table("chat_threads").select("thread_id").eq("shipment_id", shipment_id).neq("thread_status", "CLOSED").execute()
        for t in (open_threads.data or []):
            _update_rows("chat_threads", {"thread_status": "CLOSED", "closed_at": now}, {"thread_id": t["thread_id"]})

    elif body.status == "CANCELLED":
        # Cancel active appointment
        appt = get_current_appointment(shipment_id)
        if appt:
            cancel_appointment(appt["appointment_id"], reason=body.notes or "Shipment cancelled")

    logger.info(f"[admin] Shipment {shipment_id} status → {body.status}")

    return {
        "status": "updated",
        "shipment_id": shipment_id,
        "new_status": body.status,
    }


def _determine_arrival_state(shipment_id: str, gate_in_ts: str, client) -> str:
    """Determine if the truck arrived EARLY, ON_TIME, or LATE relative to its appointment slot."""
    try:
        appt_resp = (
            client.table("appointments")
            .select("slot_id, appointment_slots:slot_id(slot_start_ts, slot_end_ts)")
            .eq("shipment_id", shipment_id)
            .eq("is_current", 1)
            .in_("appointment_status", ["PENDING_CONFIRMATION", "CONFIRMED", "IN_PROGRESS"])
            .limit(1)
            .execute()
        )
        if not appt_resp.data:
            return "ON_TIME"

        slot_data = appt_resp.data[0].get("appointment_slots", {})
        slot_start = slot_data.get("slot_start_ts", "")
        if not slot_start:
            return "ON_TIME"

        gate_time = datetime.fromisoformat(gate_in_ts.replace("+05:30", "+05:30"))
        slot_time = datetime.fromisoformat(slot_start.replace("+05:30", "+05:30"))

        diff_minutes = (gate_time - slot_time).total_seconds() / 60

        if diff_minutes < -30:
            return "EARLY"
        elif diff_minutes <= 30:
            return "ON_TIME"
        else:
            return "LATE"
    except Exception:
        return "ON_TIME"


# ---------------------------------------------------------------------------
# Routes: Admin — Dashboard
# ---------------------------------------------------------------------------

@app.get("/admin/dashboard")
async def admin_dashboard(
    facility_id: Optional[str] = Query(None, description="Filter by facility ID"),
    status: Optional[str] = Query(None, description="Filter by shipment status"),
    driver_id: Optional[str] = Query(None, description="Filter by driver ID"),
    exception_type: Optional[str] = Query(None, description="Filter by exception type"),
):
    """
    Returns the full operational picture for the admin dashboard:
    - All shipments with their ETAs
    - Driver exceptions with severity and status
    - Facility info

    Supports filtering by facility, status, driver, and exception type.
    """
    from db import get_client

    client = get_client()

    # --- Shipments with ETA data ---
    shipment_query = client.table("shipments").select(
        "*, facilities:destination_facility_id(facility_name, city), "
        "drivers:driver_id(driver_name, phone), "
        "vehicles:vehicle_id(registration_number, vehicle_type_code)"
    )

    if facility_id:
        shipment_query = shipment_query.eq("destination_facility_id", facility_id)
    if status:
        shipment_query = shipment_query.eq("current_status", status)
    if driver_id:
        shipment_query = shipment_query.eq("driver_id", driver_id)

    shipment_query = shipment_query.order("latest_eta_ts")
    shipments_response = shipment_query.execute()
    shipments = shipments_response.data or []

    # --- Driver exceptions ---
    exc_query = client.table("driver_exceptions").select(
        "*, shipments:shipment_id(destination_facility_id, priority_code, "
        "required_dock_type, load_weight_kg, current_status, customer_name, "
        "product_category, original_eta_ts, latest_eta_ts), "
        "drivers:driver_id(driver_name, phone)"
    )

    if exception_type:
        exc_query = exc_query.eq("exception_type", exception_type)
    if driver_id:
        exc_query = exc_query.eq("driver_id", driver_id)

    # Only show active exceptions
    exc_query = exc_query.in_(
        "exception_status",
        ["OPEN", "NEEDS_INFORMATION", "SLOT_OPTIONS_SHARED", "WAITING_CONFIRMATION"],
    )
    exc_query = exc_query.order("reported_at", desc=True)
    exceptions_response = exc_query.execute()
    exceptions = exceptions_response.data or []

    # Filter exceptions by facility if needed (via joined shipment data)
    if facility_id and exceptions:
        exceptions = [
            e for e in exceptions
            if e.get("shipments", {}).get("destination_facility_id") == facility_id
        ]

    # --- Summary stats ---
    status_counts: dict = {}
    for s in shipments:
        st = s.get("current_status", "UNKNOWN")
        status_counts[st] = status_counts.get(st, 0) + 1

    severity_counts: dict = {}
    for e in exceptions:
        sev = e.get("severity_code", "UNKNOWN")
        severity_counts[sev] = severity_counts.get(sev, 0) + 1

    return {
        "shipments": shipments,
        "exceptions": exceptions,
        "summary": {
            "total_shipments": len(shipments),
            "status_breakdown": status_counts,
            "active_exceptions": len(exceptions),
            "severity_breakdown": severity_counts,
        },
        "facilities": get_all_facilities(),
    }


@app.get("/admin/exceptions/{exception_id}")
async def admin_exception_detail(exception_id: str):
    """Get full details of a specific exception including shipment and slot data."""
    exception = get_exception(exception_id)
    if not exception:
        raise HTTPException(status_code=404, detail="Exception not found.")

    shipment_id = exception.get("shipment_id")
    shipment = get_shipment(shipment_id) if shipment_id else None
    driver = get_driver(exception["driver_id"])
    latest_eta = get_latest_eta(shipment_id) if shipment_id else None
    current_appt = get_current_appointment(shipment_id) if shipment_id else None

    return {
        "exception": exception,
        "shipment": shipment,
        "driver": driver,
        "latest_eta": latest_eta,
        "current_appointment": current_appt,
    }


# ---------------------------------------------------------------------------
# Routes: Admin — Slot Suggestions
# ---------------------------------------------------------------------------

@app.get("/admin/suggestions/{exception_id}")
async def admin_slot_suggestions(exception_id: str):
    """
    For a given driver exception, return available slot options that the
    operations person can choose from.

    Returns:
    - Available compatible slots after the driver's declared ETA
    - Dock compatibility info (STANDARD/REEFER/HEAVY)
    - A ranked suggestion list based on priority, time proximity, and dock fit
    """
    exception = get_exception(exception_id)
    if not exception:
        raise HTTPException(status_code=404, detail="Exception not found.")

    shipment_id = exception.get("shipment_id")
    if not shipment_id:
        return {
            "exception_id": exception_id,
            "suggestions": [],
            "message": "No shipment linked to this exception. Cannot suggest slots.",
        }

    shipment = get_shipment(shipment_id)
    if not shipment:
        raise HTTPException(status_code=404, detail="Shipment not found.")

    facility_id = shipment["destination_facility_id"]
    declared_eta = exception.get("declared_eta_ts") or shipment.get("latest_eta_ts", "")
    required_dock_type = shipment.get("required_dock_type", "ANY")
    load_weight = shipment.get("load_weight_kg", 0)
    priority = shipment.get("priority_code", "NORMAL")
    unload_min = shipment.get("expected_unload_min", 60)

    # Get facility info and rules
    facility = get_facility(facility_id)
    rules = get_facility_rules(facility_id)
    docks = get_docks_by_facility(facility_id)

    # Determine compatible dock types
    compatible_dock_types = []
    if required_dock_type == "ANY" or required_dock_type == "STANDARD":
        compatible_dock_types.append("STANDARD")
    if required_dock_type == "REEFER":
        compatible_dock_types.append("REEFER")
    if required_dock_type == "HEAVY":
        compatible_dock_types.append("HEAVY")
    # Weight check: if > 25000 kg, must use HEAVY
    if load_weight > 25000 and "HEAVY" not in compatible_dock_types:
        compatible_dock_types = ["HEAVY"]

    # Get available slots for each compatible dock type
    all_available_slots = []
    for dock_type in compatible_dock_types:
        slots = get_slot_availability(
            facility_id=facility_id,
            dock_type=dock_type,
            after_ts=declared_eta,
            status="AVAILABLE",
        )
        for slot in slots:
            slot["compatible_for"] = dock_type
            all_available_slots.append(slot)

    # Sort by slot_start_ts (earliest first)
    all_available_slots.sort(key=lambda s: s.get("slot_start_ts", ""))

    # Build ranked suggestions with scoring
    suggestions = []
    for slot in all_available_slots[:15]:  # Top 15 options
        score = _score_slot(
            slot=slot,
            declared_eta=declared_eta,
            priority=priority,
            unload_min=unload_min,
            load_weight=load_weight,
        )
        suggestions.append({
            "slot_id": slot.get("slot_id"),
            "dock_code": slot.get("dock_code"),
            "dock_type": slot.get("dock_type"),
            "slot_start": slot.get("slot_start_ts"),
            "slot_end": slot.get("slot_end_ts"),
            "max_weight_kg": slot.get("max_vehicle_weight_kg"),
            "supports_refrigerated": slot.get("supports_refrigerated"),
            "score": score,
            "recommendation": _get_recommendation(score),
        })

    # Sort by score descending (higher = better fit)
    suggestions.sort(key=lambda s: s["score"], reverse=True)

    return {
        "exception_id": exception_id,
        "shipment_id": shipment_id,
        "facility_id": facility_id,
        "declared_eta": declared_eta,
        "required_dock_type": required_dock_type,
        "load_weight_kg": load_weight,
        "priority_code": priority,
        "expected_unload_min": unload_min,
        "current_appointment": get_current_appointment(shipment_id),
        "suggestions": suggestions,
        "facility": facility,
        "rules": rules,
        "compatible_docks": [
            d for d in docks if d.get("dock_type") in compatible_dock_types
        ],
    }


def _score_slot(
    slot: dict,
    declared_eta: str,
    priority: str,
    unload_min: int,
    load_weight: int,
) -> int:
    """
    Score a slot from 0-100 based on fitness for the shipment.

    Factors:
    - Time proximity to ETA (closer = better)
    - Priority match (CRITICAL/HIGH gets bonus for earliest slots)
    - Weight capacity headroom
    - Slot duration vs expected unload time
    """
    score = 50  # Base score

    # Time proximity: slots starting within 30 min of ETA are ideal
    try:
        from datetime import datetime as dt
        eta_time = dt.fromisoformat(declared_eta)
        slot_start = dt.fromisoformat(slot.get("slot_start_ts", declared_eta))
        gap_minutes = (slot_start - eta_time).total_seconds() / 60

        if gap_minutes < 0:
            score -= 20  # Slot starts before ETA — driver can't make it
        elif gap_minutes <= 15:
            score += 30  # Excellent — minimal wait
        elif gap_minutes <= 30:
            score += 25
        elif gap_minutes <= 60:
            score += 15
        elif gap_minutes <= 120:
            score += 5
        else:
            score -= 5  # Very far out
    except (ValueError, TypeError):
        pass

    # Priority bonus for early slots
    if priority in ("CRITICAL", "HIGH"):
        score += 10

    # Weight headroom
    max_weight = slot.get("max_vehicle_weight_kg", 35000)
    if max_weight and load_weight:
        headroom_pct = ((max_weight - load_weight) / max_weight) * 100
        if headroom_pct > 20:
            score += 5
        elif headroom_pct < 5:
            score -= 10  # Too tight

    # Cap score
    return max(0, min(100, score))


def _get_recommendation(score: int) -> str:
    """Convert score to a human-readable recommendation label."""
    if score >= 80:
        return "HIGHLY_RECOMMENDED"
    elif score >= 60:
        return "RECOMMENDED"
    elif score >= 40:
        return "ACCEPTABLE"
    elif score >= 20:
        return "SUB_OPTIMAL"
    else:
        return "NOT_RECOMMENDED"


# ---------------------------------------------------------------------------
# Routes: Admin — Approve / Reassign Exception
# ---------------------------------------------------------------------------

class ApproveExceptionRequest(BaseModel):
    slot_id: str = Field(..., description="The slot to assign to the shipment")
    notes: Optional[str] = Field(None, description="Operations notes")


@app.post("/admin/exceptions/{exception_id}/approve")
async def admin_approve_exception(exception_id: str, body: ApproveExceptionRequest):
    """
    Approve a driver's requested ETA by assigning a specific slot.

    Flow:
    1. Cancel the existing appointment (if any)
    2. Create a new appointment with the chosen slot
    3. Update the shipment's latest ETA
    4. Mark the exception as RESOLVED
    """
    exception = get_exception(exception_id)
    if not exception:
        raise HTTPException(status_code=404, detail="Exception not found.")

    shipment_id = exception.get("shipment_id")
    if not shipment_id:
        raise HTTPException(status_code=400, detail="No shipment linked to this exception.")

    shipment = get_shipment(shipment_id)
    if not shipment:
        raise HTTPException(status_code=404, detail="Shipment not found.")

    now = _now_iso()

    # 1. Cancel existing appointment if any
    existing_appt = get_current_appointment(shipment_id)
    if existing_appt:
        cancel_appointment(
            existing_appt["appointment_id"],
            reason=f"Reassigned due to exception {exception_id}",
        )
        logger.info(f"[admin] Cancelled appointment {existing_appt['appointment_id']}")

    # 2. Create new appointment
    new_appt_id = f"APT-{uuid.uuid4().hex[:8].upper()}"
    create_appointment({
        "appointment_id": new_appt_id,
        "shipment_id": shipment_id,
        "slot_id": body.slot_id,
        "appointment_status": "CONFIRMED",
        "booking_source": "MANUAL_OVERRIDE",
        "is_current": 1,
        "booked_at": now,
        "confirmed_at": now,
        "updated_at": now,
        "warehouse_confirmation_ref": None,
        "replaced_appointment_id": existing_appt["appointment_id"] if existing_appt else None,
    })
    logger.info(f"[admin] Created appointment {new_appt_id} for slot {body.slot_id}")

    # 3. Update shipment ETA to match the declared ETA
    declared_eta = exception.get("declared_eta_ts")
    if declared_eta:
        update_shipment_eta(shipment_id, declared_eta)

    # 4. Resolve the exception
    update_data = {
        "exception_status": "RESOLVED",
        "description": exception.get("description", "") + f" | Resolved: assigned slot {body.slot_id}",
    }
    if body.notes:
        update_data["description"] += f" | Ops notes: {body.notes}"
    update_exception(exception_id, update_data)

    # 5. Update thread_status to RESOLVED
    thread_id = exception.get("thread_id")
    if thread_id:
        from db import _update_rows as _ur
        _ur("chat_threads", {"thread_status": "RESOLVED"}, {"thread_id": thread_id})

    logger.info(f"[admin] Exception {exception_id} resolved with slot {body.slot_id}")

    return {
        "status": "approved",
        "exception_id": exception_id,
        "appointment_id": new_appt_id,
        "slot_id": body.slot_id,
        "shipment_id": shipment_id,
    }


class EscalateExceptionRequest(BaseModel):
    reason: str = Field(..., description="Reason for escalation")


@app.post("/admin/exceptions/{exception_id}/escalate")
async def admin_escalate_exception(exception_id: str, body: EscalateExceptionRequest):
    """Mark an exception as escalated when no feasible slot exists."""
    exception = get_exception(exception_id)
    if not exception:
        raise HTTPException(status_code=404, detail="Exception not found.")

    update_exception(exception_id, {
        "exception_status": "ESCALATED",
        "description": exception.get("description", "") + f" | Escalated: {body.reason}",
    })

    return {"status": "escalated", "exception_id": exception_id, "reason": body.reason}


# ---------------------------------------------------------------------------
# Routes: Admin — Filter Options
# ---------------------------------------------------------------------------

@app.get("/admin/filters")
async def admin_filter_options():
    """Return available filter values for the admin dashboard dropdowns."""
    from db import get_client as _gc, get_all_carriers

    client = _gc()

    # Unique drivers with shipments
    drivers_resp = client.table("drivers").select("driver_id, driver_name").eq("driver_status", "ACTIVE").execute()

    return {
        "facilities": get_all_facilities(),
        "drivers": drivers_resp.data or [],
        "statuses": [
            "PLANNED", "ASSIGNED", "IN_TRANSIT", "AT_GATE",
            "WAITING", "IN_DOCK", "COMPLETED", "CANCELLED",
        ],
        "exception_types": [
            "DELAY", "BREAKDOWN", "TRAFFIC", "WEATHER",
            "EARLY_ARRIVAL", "DOCK_UNAVAILABLE", "UNKNOWN",
        ],
        "severities": ["LOW", "MEDIUM", "HIGH", "CRITICAL"],
        "carriers": get_all_carriers(),
    }


# ---------------------------------------------------------------------------
# Routes: Admin — ETA Override
# ---------------------------------------------------------------------------

class EtaOverrideRequest(BaseModel):
    slot_id: str = Field(..., description="Primary slot (first in sequence)")
    slot_ids: Optional[list[str]] = Field(None, description="All consecutive slot IDs (1-3)")
    notes: Optional[str] = Field(None, description="Reason for the override")


@app.patch("/admin/shipments/{shipment_id}/eta-override")
async def admin_eta_override(shipment_id: str, body: EtaOverrideRequest):
    """
    Operations person overrides the ETA and reassigns a slot.

    Flow:
    1. Cancel existing appointment (if any)
    2. Create new appointment with the chosen slot
    3. Insert eta_updates record with source_type='OPERATIONS_OVERRIDE'
    4. Update shipment.latest_eta_ts to the slot start time
    5. Resolve any open exceptions for this shipment

    This is distinct from driver-requested ETA changes (DRIVER_DECLARED).
    """
    from db import _insert_row, _update_rows, get_client as _gc

    shipment = get_shipment(shipment_id)
    if not shipment:
        raise HTTPException(status_code=404, detail="Shipment not found.")

    now = _now_iso()

    # Get slot info for the new ETA
    client = _gc()
    slot_resp = client.table("appointment_slots").select("*").eq("slot_id", body.slot_id).limit(1).execute()
    if not slot_resp.data:
        raise HTTPException(status_code=400, detail="Slot not found.")

    slot = slot_resp.data[0]
    new_eta = slot["slot_start_ts"]

    # 1. Cancel all existing active appointments for this shipment
    existing_appt = get_current_appointment(shipment_id)
    if existing_appt:
        # Cancel all current appointments
        from db import get_client as _gc2
        client2 = _gc2()
        all_current = client2.table("appointments").select("appointment_id").eq("shipment_id", shipment_id).eq("is_current", 1).in_(
            "appointment_status", ["PENDING_CONFIRMATION", "CONFIRMED", "IN_PROGRESS"]
        ).execute()
        for appt in (all_current.data or []):
            cancel_appointment(
                appt["appointment_id"],
                reason=f"Operations ETA override: {body.notes or 'Manual reassignment'}",
            )

    # 2. Create appointments for all selected slots
    all_slot_ids = body.slot_ids if body.slot_ids else [body.slot_id]
    new_appt_id = ""
    for sid in all_slot_ids:
        appt_id = f"APT-{uuid.uuid4().hex[:8].upper()}"
        if not new_appt_id:
            new_appt_id = appt_id  # Track the first for response
        _insert_row("appointments", {
            "appointment_id": appt_id,
            "shipment_id": shipment_id,
            "slot_id": sid,
            "appointment_status": "CONFIRMED",
            "booking_source": "MANUAL_OVERRIDE",
            "is_current": 1,
            "booked_at": now,
            "confirmed_at": now,
            "cancelled_at": None,
            "cancellation_reason": None,
            "replaced_appointment_id": existing_appt["appointment_id"] if existing_appt else None,
            "warehouse_confirmation_ref": None,
            "updated_at": now,
        })

    # 3. Insert ETA update with OPERATIONS_OVERRIDE source
    eta_id = f"ETA-{uuid.uuid4().hex[:8].upper()}"
    _insert_row("eta_updates", {
        "eta_update_id": eta_id,
        "shipment_id": shipment_id,
        "source_type": "OPERATIONS_OVERRIDE",
        "reported_by_driver_id": None,
        "declared_eta_ts": new_eta,
        "confidence_code": "HIGH",
        "delay_reason_code": None,
        "note": body.notes or "Operations manual ETA override",
        "created_at": now,
    })

    # 4. Update shipment latest_eta_ts
    _update_rows("shipments", {"latest_eta_ts": new_eta, "updated_at": now}, {"shipment_id": shipment_id})

    # 5. Resolve any open exceptions for this shipment
    open_excs = client.table("driver_exceptions").select("exception_id").eq("shipment_id", shipment_id).in_(
        "exception_status", ["OPEN", "NEEDS_INFORMATION", "WAITING_CONFIRMATION"]
    ).execute()
    for exc in (open_excs.data or []):
        _update_rows("driver_exceptions", {
            "exception_status": "RESOLVED",
        }, {"exception_id": exc["exception_id"]})

    logger.info(f"[admin] ETA override for {shipment_id}: slot={body.slot_id}, eta={new_eta}")

    return {
        "status": "updated",
        "shipment_id": shipment_id,
        "appointment_id": new_appt_id,
        "slot_id": body.slot_id,
        "new_eta": new_eta,
    }


@app.get("/admin/drivers/{driver_id}")
async def admin_get_driver_detail(driver_id: str):
    """Get full driver info for the popup display."""
    from db import get_client as _gc

    driver = get_driver(driver_id)
    if not driver:
        raise HTTPException(status_code=404, detail="Driver not found.")

    client = _gc()
    carrier_resp = client.table("carriers").select("carrier_name, contact_phone").eq("carrier_id", driver["carrier_id"]).limit(1).execute()
    carrier = carrier_resp.data[0] if carrier_resp.data else {}

    return {
        "driver_id": driver["driver_id"],
        "driver_name": driver["driver_name"],
        "phone": driver["phone"],
        "licence_number": driver["licence_number"],
        "home_base_city": driver.get("home_base_city"),
        "driver_status": driver["driver_status"],
        "carrier_id": driver["carrier_id"],
        "carrier_name": carrier.get("carrier_name", ""),
        "carrier_phone": carrier.get("contact_phone", ""),
    }


# ---------------------------------------------------------------------------
# Routes: Admin — Slot Management
# ---------------------------------------------------------------------------

class GenerateSlotsRequest(BaseModel):
    start_date: str = Field(..., description="Start date YYYY-MM-DD")
    end_date: str = Field(..., description="End date YYYY-MM-DD")


class UpdateSlotRequest(BaseModel):
    slot_status: str = Field(..., description="New status: OPEN, BLOCKED, or CLOSED")
    block_reason: Optional[str] = Field(None, description="Reason for blocking")


@app.post("/admin/slots/generate")
async def admin_generate_slots(body: GenerateSlotsRequest):
    """
    Generate 1-hour appointment slots for all docks across all facilities
    for the given date range. Existing slots are not duplicated (upsert).
    """
    from generate_slots import generate_slots_for_range, insert_slots

    try:
        start = datetime.strptime(body.start_date, "%Y-%m-%d")
        end = datetime.strptime(body.end_date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail="Dates must be in YYYY-MM-DD format.")

    if end < start:
        raise HTTPException(status_code=400, detail="end_date must be >= start_date.")
    if (end - start).days > 30:
        raise HTTPException(status_code=400, detail="Maximum range is 30 days.")

    slots = generate_slots_for_range(start, end)
    inserted = insert_slots(slots)

    logger.info(f"[slots] Generated {len(slots)}, inserted {inserted} for {body.start_date} to {body.end_date}")

    return {
        "status": "success",
        "start_date": body.start_date,
        "end_date": body.end_date,
        "total_generated": len(slots),
        "total_inserted": inserted,
    }


@app.get("/admin/slots")
async def admin_list_slots(
    facility_id: str = Query(..., description="Facility ID"),
    date: Optional[str] = Query(None, description="Date filter YYYY-MM-DD"),
    dock_id: Optional[str] = Query(None, description="Filter by dock ID"),
    status: Optional[str] = Query(None, description="Filter by slot status"),
):
    """List slots for a facility with optional date/dock/status filters."""
    from db import get_client as _gc

    client = _gc()
    query = client.table("appointment_slots").select("*").eq("facility_id", facility_id)

    if dock_id:
        query = query.eq("dock_id", dock_id)
    if status:
        query = query.eq("slot_status", status)
    if date:
        day_start = f"{date}T00:00:00+05:30"
        day_end = f"{date}T23:59:59+05:30"
        query = query.gte("slot_start_ts", day_start).lte("slot_start_ts", day_end)

    query = query.order("slot_start_ts").limit(500)
    response = query.execute()

    return {"slots": response.data or [], "count": len(response.data or [])}


@app.patch("/admin/slots/{slot_id}")
async def admin_update_slot(slot_id: str, body: UpdateSlotRequest):
    """Update a slot's status (OPEN, BLOCKED, CLOSED)."""
    from db import _update_rows

    if body.slot_status not in ("OPEN", "BLOCKED", "CLOSED"):
        raise HTTPException(status_code=400, detail="Status must be OPEN, BLOCKED, or CLOSED.")

    update_data: dict = {"slot_status": body.slot_status}
    if body.slot_status == "BLOCKED" and body.block_reason:
        update_data["block_reason"] = body.block_reason
    elif body.slot_status == "OPEN":
        update_data["block_reason"] = None

    result = _update_rows("appointment_slots", update_data, {"slot_id": slot_id})
    if not result:
        raise HTTPException(status_code=404, detail="Slot not found.")

    return {"status": "updated", "slot_id": slot_id, "new_status": body.slot_status}


@app.patch("/admin/slots/bulk-update")
async def admin_bulk_update_slots(
    slot_ids: list[str],
    status: str = Query(..., description="New status"),
    block_reason: Optional[str] = Query(None, description="Reason (for BLOCKED)"),
):
    """Bulk update multiple slots to the same status."""
    from db import get_client as _gc

    if status not in ("OPEN", "BLOCKED", "CLOSED"):
        raise HTTPException(status_code=400, detail="Status must be OPEN, BLOCKED, or CLOSED.")

    client = _gc()
    update_data: dict = {"slot_status": status}
    if status == "BLOCKED" and block_reason:
        update_data["block_reason"] = block_reason
    elif status == "OPEN":
        update_data["block_reason"] = None

    response = client.table("appointment_slots").update(update_data).in_("slot_id", slot_ids).execute()

    return {"status": "updated", "count": len(response.data or []), "new_status": status}


# ---------------------------------------------------------------------------
# Routes: Admin — Create Shipment
# ---------------------------------------------------------------------------
class CreateShipmentRequest(BaseModel):
    """All fields needed to create a shipment and auto-assign an appointment."""
    carrier_id: str
    driver_id: str
    vehicle_id: str
    origin_name: str
    origin_city: str
    destination_facility_id: str
    customer_name: str
    product_category: str
    load_weight_kg: int = Field(..., gt=0)
    pallet_count: Optional[int] = Field(None, ge=0)
    required_dock_type: str = Field(default="STANDARD")
    temperature_control_required: bool = Field(default=False)
    priority_code: str = Field(default="NORMAL")
    planned_departure_ts: str = Field(..., description="ISO-8601 planned departure")
    original_eta_ts: str = Field(..., description="ISO-8601 estimated arrival")
    expected_unload_min: int = Field(default=60, gt=0)
    slot_id: str = Field(..., description="Primary slot (first in sequence)")
    slot_ids: Optional[list[str]] = Field(None, description="All consecutive slot IDs (1-3)")


@app.get("/admin/shipments/form-data")
async def get_shipment_form_data():
    """
    Returns all dropdown data needed for the shipment creation form:
    carriers, drivers, vehicles, facilities, docks, and available slots.
    """
    from db import get_client as _gc

    client = _gc()

    carriers = client.table("carriers").select("*").eq("active_flag", 1).execute()
    drivers = client.table("drivers").select("*, carriers(carrier_name)").eq("driver_status", "ACTIVE").execute()
    vehicles = client.table("vehicles").select("*, vehicle_types(description, typical_dock_type, refrigerated_flag)").eq("active_flag", 1).execute()
    facilities = client.table("facilities").select("*").eq("active_flag", 1).execute()
    docks = client.table("docks").select("*").execute()

    return {
        "carriers": carriers.data or [],
        "drivers": drivers.data or [],
        "vehicles": vehicles.data or [],
        "facilities": facilities.data or [],
        "docks": docks.data or [],
    }


@app.get("/admin/shipments/available-slots")
async def get_available_slots_for_form(
    facility_id: str = Query(..., description="Facility ID"),
    dock_type: Optional[str] = Query(None, description="Dock type filter"),
    after_ts: Optional[str] = Query(None, description="ETA reference timestamp"),
    include_all: bool = Query(False, description="Include blocked/closed slots and slots before ETA for calendar view"),
):
    """
    Fetch slots for appointment assignment.
    If include_all=True, returns all slots for the ETA date (including blocked/before-ETA)
    with availability_status field for the calendar view.
    If include_all=False, returns only AVAILABLE slots after the given timestamp.
    """
    if include_all and after_ts:
        # Get all slots for the ETA date and the day before (for calendar view)
        eta_date = after_ts.split("T")[0]
        day_start = f"{eta_date}T00:00:00+05:30"

        from db import get_client as _gc
        client = _gc()
        query = (
            client.table("v_slot_availability")
            .select("*")
            .eq("facility_id", facility_id)
            .gte("slot_start_ts", day_start)
        )
        if dock_type and dock_type != "ANY":
            query = query.eq("dock_type", dock_type)

        response = query.order("slot_start_ts").limit(500).execute()
        return {"slots": response.data or []}
    else:
        slots = get_slot_availability(
            facility_id=facility_id,
            dock_type=dock_type if dock_type and dock_type != "ANY" else None,
            after_ts=after_ts,
            status="AVAILABLE",
        )
        return {"slots": slots}


@app.post("/admin/shipments/create")
async def create_shipment(body: CreateShipmentRequest):
    """
    Create a new shipment with automatic appointment and ETA record.

    Inserts into:
    1. shipments — the freight movement record
    2. appointments — links shipment to the chosen slot
    3. eta_updates — initial planned ETA record

    Returns the created shipment_id and appointment_id.
    """
    from db import _insert_row

    now = _now_iso()

    # Generate IDs
    short_uuid = uuid.uuid4().hex[:6].upper()
    shipment_id = f"SHP-{short_uuid}"
    order_ref = f"ORD-{datetime.now().strftime('%y%m%d')}-{short_uuid}"
    appointment_id = f"APT-{uuid.uuid4().hex[:8].upper()}"
    eta_id = f"ETA-{uuid.uuid4().hex[:8].upper()}"

    # Validate referenced entities exist
    driver = get_driver(body.driver_id)
    if not driver:
        raise HTTPException(status_code=400, detail=f"Driver {body.driver_id} not found.")

    vehicle = get_vehicle(body.vehicle_id)
    if not vehicle:
        raise HTTPException(status_code=400, detail=f"Vehicle {body.vehicle_id} not found.")

    facility = get_facility(body.destination_facility_id)
    if not facility:
        raise HTTPException(status_code=400, detail=f"Facility {body.destination_facility_id} not found.")

    # 1. Insert shipment
    shipment_data = {
        "shipment_id": shipment_id,
        "order_reference": order_ref,
        "carrier_id": body.carrier_id,
        "driver_id": body.driver_id,
        "vehicle_id": body.vehicle_id,
        "origin_name": body.origin_name,
        "origin_city": body.origin_city,
        "destination_facility_id": body.destination_facility_id,
        "customer_name": body.customer_name,
        "product_category": body.product_category,
        "load_weight_kg": body.load_weight_kg,
        "pallet_count": body.pallet_count,
        "required_dock_type": body.required_dock_type,
        "temperature_control_required": 1 if body.temperature_control_required else 0,
        "priority_code": body.priority_code,
        "planned_departure_ts": body.planned_departure_ts,
        "actual_departure_ts": None,
        "original_eta_ts": body.original_eta_ts,
        "latest_eta_ts": body.original_eta_ts,
        "expected_unload_min": body.expected_unload_min,
        "current_status": "PLANNED",
        "created_at": now,
        "updated_at": now,
    }

    try:
        _insert_row("shipments", shipment_data)
        logger.info(f"[shipment] Created shipment {shipment_id}")
    except Exception as e:
        logger.error(f"[shipment] Failed to create shipment: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create shipment: {e}")

    # 2. Insert appointments for all selected slots (1-3 consecutive)
    all_slot_ids = body.slot_ids if body.slot_ids else [body.slot_id]
    appointment_ids = []

    for i, sid in enumerate(all_slot_ids):
        appt_id = f"APT-{uuid.uuid4().hex[:8].upper()}"
        appointment_ids.append(appt_id)
        appointment_data = {
            "appointment_id": appt_id,
            "shipment_id": shipment_id,
            "slot_id": sid,
            "appointment_status": "CONFIRMED",
            "booking_source": "PLANNER",
            "is_current": 1,
            "booked_at": now,
            "confirmed_at": now,
            "cancelled_at": None,
            "cancellation_reason": None,
            "replaced_appointment_id": None,
            "warehouse_confirmation_ref": None,
            "updated_at": now,
        }

        try:
            _insert_row("appointments", appointment_data)
            logger.info(f"[shipment] Created appointment {appt_id} for slot {sid} ({i+1}/{len(all_slot_ids)})")
        except Exception as e:
            logger.error(f"[shipment] Failed to create appointment for slot {sid}: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to create appointment: {e}")

    # 3. Insert initial ETA record
    eta_data = {
        "eta_update_id": eta_id,
        "shipment_id": shipment_id,
        "source_type": "ORIGINAL_PLAN",
        "reported_by_driver_id": None,
        "declared_eta_ts": body.original_eta_ts,
        "confidence_code": "HIGH",
        "delay_reason_code": None,
        "note": "Initial planned ETA at shipment creation.",
        "created_at": now,
    }

    try:
        _insert_row("eta_updates", eta_data)
        logger.info(f"[shipment] Created ETA record {eta_id}")
    except Exception as e:
        logger.warning(f"[shipment] Failed to create ETA record (non-critical): {e}")

    return {
        "status": "created",
        "shipment_id": shipment_id,
        "order_reference": order_ref,
        "appointment_id": appointment_ids[0],
        "appointment_ids": appointment_ids,
        "slot_id": body.slot_id,
        "slot_ids": all_slot_ids,
        "driver_id": body.driver_id,
        "facility_id": body.destination_facility_id,
    }


# ---------------------------------------------------------------------------
# Entry Point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(
        "server:app",
        host="0.0.0.0",
        port=port,
        reload=os.environ.get("ENV", "development") == "development",
        log_level="info",
    )
