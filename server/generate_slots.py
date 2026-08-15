"""
SetuHaul — Generate Weekly Appointment Slots

Generates 1-hour slots for all docks across all facilities for a given date range.
Can be run standalone or called from the admin API.

Usage:
    python generate_slots.py                     # Generates for this week (Mon-Sun)
    python generate_slots.py 2026-08-10 2026-08-16  # Custom range
"""

import sys
import os
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

from dotenv import load_dotenv
load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent / ".env")

from db import get_client, get_all_facilities, get_docks_by_facility


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Facility operating hours (start_hour, end_hour)
FACILITY_HOURS = {
    "FAC-JAI-01": (6, 22),   # 06:00–22:00 → 16 slots
    "FAC-GGN-01": (7, 21),   # 07:00–21:00 → 14 slots
}

# Fallback if facility not in map
DEFAULT_HOURS = (6, 22)

TIMEZONE_OFFSET = "+05:30"
SLOT_DURATION_HOURS = 1


# ---------------------------------------------------------------------------
# Slot Generation
# ---------------------------------------------------------------------------

def generate_slot_id(facility_id: str, dock_code: str, date: datetime, hour: int) -> str:
    """Generate a unique slot ID.
    Format: SLOT-JAI-D1-260810-06
    """
    fac_short = facility_id.split("-")[1]  # JAI or GGN
    date_str = date.strftime("%y%m%d")
    return f"SLOT-{fac_short}-{dock_code}-{date_str}-{hour:02d}"


def generate_slots_for_range(
    start_date: datetime,
    end_date: datetime,
    facilities: Optional[list] = None,
) -> list[dict]:
    """
    Generate slot records for all docks across all facilities for the given date range.

    Returns a list of dicts ready for insertion into appointment_slots.
    """
    if facilities is None:
        facilities = get_all_facilities()

    created_at = datetime.now().strftime(f"%Y-%m-%dT%H:%M:%S{TIMEZONE_OFFSET}")
    slots = []

    current_date = start_date
    while current_date <= end_date:
        for facility in facilities:
            fac_id = facility["facility_id"]
            start_hour, end_hour = FACILITY_HOURS.get(fac_id, DEFAULT_HOURS)
            docks = get_docks_by_facility(fac_id)

            for dock in docks:
                dock_id = dock["dock_id"]
                dock_code = dock["dock_code"]

                for hour in range(start_hour, end_hour):
                    slot_start = current_date.replace(hour=hour, minute=0, second=0)
                    slot_end = slot_start + timedelta(hours=SLOT_DURATION_HOURS)

                    slot_id = generate_slot_id(fac_id, dock_code, current_date, hour)

                    slots.append({
                        "slot_id": slot_id,
                        "facility_id": fac_id,
                        "dock_id": dock_id,
                        "slot_start_ts": slot_start.strftime(f"%Y-%m-%dT%H:%M:%S{TIMEZONE_OFFSET}"),
                        "slot_end_ts": slot_end.strftime(f"%Y-%m-%dT%H:%M:%S{TIMEZONE_OFFSET}"),
                        "slot_status": "OPEN",
                        "block_reason": None,
                        "created_at": created_at,
                    })

        current_date += timedelta(days=1)

    return slots


def insert_slots(slots: list[dict], batch_size: int = 100) -> int:
    """
    Insert slots into the appointment_slots table in batches.
    Skips duplicates (upsert on conflict with slot_id).

    Returns total inserted count.
    """
    client = get_client()
    total_inserted = 0

    for i in range(0, len(slots), batch_size):
        batch = slots[i:i + batch_size]
        try:
            # Use upsert to skip already-existing slots
            response = client.table("appointment_slots").upsert(
                batch, on_conflict="slot_id"
            ).execute()
            total_inserted += len(response.data) if response.data else 0
        except Exception as e:
            print(f"  Batch {i // batch_size + 1} failed: {e}")

    return total_inserted


def generate_and_insert_week(start_date: Optional[datetime] = None) -> dict:
    """
    Generate slots for a full week starting from start_date (defaults to today/Monday).

    Returns summary with counts.
    """
    if start_date is None:
        # Find this Monday
        today = datetime.now()
        start_date = today - timedelta(days=today.weekday())  # Monday
        start_date = start_date.replace(hour=0, minute=0, second=0, microsecond=0)

    end_date = start_date + timedelta(days=6)  # Sunday

    print(f"Generating slots: {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")

    slots = generate_slots_for_range(start_date, end_date)
    print(f"Generated {len(slots)} slot records")

    inserted = insert_slots(slots)
    print(f"Inserted/updated {inserted} slots in database")

    return {
        "start_date": start_date.strftime("%Y-%m-%d"),
        "end_date": end_date.strftime("%Y-%m-%d"),
        "total_generated": len(slots),
        "total_inserted": inserted,
    }


# ---------------------------------------------------------------------------
# CLI Entry Point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if len(sys.argv) >= 3:
        start = datetime.strptime(sys.argv[1], "%Y-%m-%d")
        end = datetime.strptime(sys.argv[2], "%Y-%m-%d")
        slots = generate_slots_for_range(start, end)
        print(f"Generated {len(slots)} slots")
        inserted = insert_slots(slots)
        print(f"Inserted {inserted} slots")
    else:
        result = generate_and_insert_week()
        print(f"\nDone: {result}")
