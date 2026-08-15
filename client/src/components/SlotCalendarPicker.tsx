import { useState, useMemo, useCallback } from "react";

/**
 * SlotCalendarPicker — Calendar-style slot grid with multi-slot selection (1-3 consecutive).
 * Shows top 3 recommended slots above the grid.
 *
 * Props:
 * - multiSelect: enables selecting 1-3 consecutive slots on the same dock
 * - maxSlots: maximum number of consecutive slots (default 3)
 * - selectedSlots: array of selected slot IDs
 * - onSelectSlots: callback with array of selected slot IDs
 *
 * Backward compatible: also supports single-select via selectedSlot/onSelect.
 */

export interface CalendarSlot {
  slot_id: string;
  dock_code: string;
  dock_type: string;
  slot_start_ts: string;
  slot_end_ts: string;
  max_vehicle_weight_kg: number;
  supports_refrigerated: number;
  availability_status?: string;
  score?: number;
  recommendation?: string;
}

interface SlotCalendarPickerProps {
  slots: CalendarSlot[];
  declaredEta?: string;
  loading?: boolean;
  maxSlots?: number;
  // Multi-select mode
  selectedSlots?: string[];
  onSelectSlots?: (slotIds: string[]) => void;
  // Single-select mode (backward compat)
  selectedSlot?: string;
  onSelect?: (slotId: string) => void;
}

function SlotCalendarPicker({
  slots,
  declaredEta,
  loading,
  maxSlots = 3,
  selectedSlots: selectedSlotsProp,
  onSelectSlots,
  selectedSlot: selectedSlotSingle,
  onSelect: onSelectSingle,
}: SlotCalendarPickerProps) {
  const [dateFilter, setDateFilter] = useState<string>("");

  // Normalize to multi-select internally
  const isMultiMode = !!onSelectSlots;
  const selectedSlots = isMultiMode
    ? (selectedSlotsProp || [])
    : selectedSlotSingle
      ? [selectedSlotSingle]
      : [];

  // Group slots by date
  const slotsByDate = useMemo(() => {
    const groups: Record<string, CalendarSlot[]> = {};
    for (const slot of slots) {
      const dateKey = slot.slot_start_ts.split("T")[0];
      if (!groups[dateKey]) groups[dateKey] = [];
      groups[dateKey].push(slot);
    }
    return groups;
  }, [slots]);

  const availableDates = useMemo(() => Object.keys(slotsByDate).sort(), [slotsByDate]);
  const activeDate = dateFilter || (declaredEta ? declaredEta.split("T")[0] : availableDates[0] || "");
  const daySlots = slotsByDate[activeDate] || [];

  // Group by dock, sorted by time
  const slotsByDock = useMemo(() => {
    const groups: Record<string, CalendarSlot[]> = {};
    for (const slot of daySlots) {
      if (!groups[slot.dock_code]) groups[slot.dock_code] = [];
      groups[slot.dock_code].push(slot);
    }
    for (const key of Object.keys(groups)) {
      groups[key].sort((a, b) => a.slot_start_ts.localeCompare(b.slot_start_ts));
    }
    return groups;
  }, [daySlots]);

  const dockCodes = useMemo(() => Object.keys(slotsByDock).sort(), [slotsByDock]);

  // Top 3 recommendations
  const topRecommended = useMemo(() => {
    const available = slots.filter((s) => (s.availability_status || "AVAILABLE") === "AVAILABLE");
    if (available.some((s) => s.score !== undefined)) {
      return [...available].sort((a, b) => (b.score || 0) - (a.score || 0)).slice(0, 3);
    }
    if (declaredEta) {
      const etaTime = new Date(declaredEta).getTime();
      return [...available]
        .sort((a, b) => Math.abs(new Date(a.slot_start_ts).getTime() - etaTime) - Math.abs(new Date(b.slot_start_ts).getTime() - etaTime))
        .slice(0, 3);
    }
    return available.slice(0, 3);
  }, [slots, declaredEta]);

  /**
   * Handle slot click with consecutive-slot logic:
   * - First click: select the slot
   * - Second click on adjacent slot (same dock): extend selection
   * - Click on non-adjacent or different dock: reset and start fresh
   * - Click on already-selected: deselect it (and any after it)
   * - Max selection: maxSlots
   */
  const handleSlotClick = useCallback(
    (clickedSlotId: string) => {
      const clickedSlot = slots.find((s) => s.slot_id === clickedSlotId);
      if (!clickedSlot) return;

      if (isMultiMode && onSelectSlots) {
        // If already selected, deselect from this point
        const idx = selectedSlots.indexOf(clickedSlotId);
        if (idx !== -1) {
          onSelectSlots(selectedSlots.slice(0, idx));
          return;
        }

        // If no selection yet, start fresh
        if (selectedSlots.length === 0) {
          onSelectSlots([clickedSlotId]);
          return;
        }

        // Check if consecutive on same dock
        const lastSelectedId = selectedSlots[selectedSlots.length - 1];
        const lastSlot = slots.find((s) => s.slot_id === lastSelectedId);

        if (!lastSlot || lastSlot.dock_code !== clickedSlot.dock_code) {
          // Different dock — reset
          onSelectSlots([clickedSlotId]);
          return;
        }

        // Check if it's the next consecutive slot
        const dockSlots = slotsByDock[clickedSlot.dock_code] || [];
        const lastIdx = dockSlots.findIndex((s) => s.slot_id === lastSelectedId);
        const clickedIdx = dockSlots.findIndex((s) => s.slot_id === clickedSlotId);

        if (clickedIdx === lastIdx + 1 && selectedSlots.length < maxSlots) {
          // It's consecutive — extend
          onSelectSlots([...selectedSlots, clickedSlotId]);
        } else {
          // Not consecutive or max reached — reset
          onSelectSlots([clickedSlotId]);
        }
      } else if (onSelectSingle) {
        onSelectSingle(clickedSlotId);
      }
    },
    [slots, selectedSlots, isMultiMode, onSelectSlots, onSelectSingle, slotsByDock, maxSlots]
  );

  if (loading) {
    return <div className="cal-picker__loading">Loading slots...</div>;
  }

  if (slots.length === 0) {
    return <div className="cal-picker__empty">No slots available for the selected criteria.</div>;
  }

  const selectedSet = new Set(selectedSlots);

  return (
    <div className="cal-picker">
      {/* Selection info */}
      {isMultiMode && selectedSlots.length > 0 && (
        <div className="cal-picker__selection-info">
          Selected: {selectedSlots.length} slot{selectedSlots.length > 1 ? "s" : ""} (max {maxSlots})
          {selectedSlots.length < maxSlots && (
            <span className="cal-picker__selection-hint"> — Click the next adjacent slot to extend</span>
          )}
        </div>
      )}

      {/* Top Recommendations */}
      {topRecommended.length > 0 && (
        <div className="cal-picker__recommendations">
          <p className="cal-picker__rec-title">Recommended Slots</p>
          <div className="cal-picker__rec-list">
            {topRecommended.map((slot, i) => (
              <button
                key={slot.slot_id}
                type="button"
                className={`cal-picker__rec-item ${selectedSet.has(slot.slot_id) ? "cal-picker__rec-item--selected" : ""}`}
                onClick={() => handleSlotClick(slot.slot_id)}
              >
                <span className="cal-picker__rec-rank">#{i + 1}</span>
                <span className="cal-picker__rec-dock">{slot.dock_code}</span>
                <span className="cal-picker__rec-time">
                  {fmtShortTime(slot.slot_start_ts)} – {fmtShortTime(slot.slot_end_ts)}
                </span>
                <span className="cal-picker__rec-date">{fmtShortDate(slot.slot_start_ts)}</span>
                {slot.score !== undefined && (
                  <span className={`cal-picker__rec-score score--${getScoreClass(slot.score)}`}>
                    {slot.score}
                  </span>
                )}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Date Tabs */}
      <div className="cal-picker__dates">
        {availableDates.map((date) => (
          <button
            key={date}
            type="button"
            className={`cal-picker__date-tab ${date === activeDate ? "cal-picker__date-tab--active" : ""}`}
            onClick={() => setDateFilter(date)}
          >
            {fmtDateTab(date)}
          </button>
        ))}
      </div>

      {/* Calendar Grid */}
      <div className="cal-picker__grid">
        {dockCodes.length === 0 ? (
          <p className="cal-picker__empty">No slots for this date.</p>
        ) : (
          dockCodes.map((dock) => (
            <div key={dock} className="cal-picker__dock-row">
              <div className="cal-picker__dock-label">{dock}</div>
              <div className="cal-picker__slots">
                {slotsByDock[dock].map((slot) => {
                  const isAvailable = (slot.availability_status || "AVAILABLE") === "AVAILABLE";
                  const isSelected = selectedSet.has(slot.slot_id);
                  const isBeforeEta = declaredEta ? slot.slot_start_ts < declaredEta : false;

                  return (
                    <button
                      key={slot.slot_id}
                      type="button"
                      className={[
                        "cal-picker__slot",
                        isAvailable ? "cal-picker__slot--available" : "cal-picker__slot--blocked",
                        isSelected ? "cal-picker__slot--selected" : "",
                        isBeforeEta && isAvailable ? "cal-picker__slot--before-eta" : "",
                      ].join(" ")}
                      onClick={() => isAvailable && handleSlotClick(slot.slot_id)}
                      disabled={!isAvailable}
                      title={`${slot.dock_code} | ${fmtShortTime(slot.slot_start_ts)}–${fmtShortTime(slot.slot_end_ts)} | ${isAvailable ? "Available" : "Blocked"}`}
                    >
                      {fmtHour(slot.slot_start_ts)}
                    </button>
                  );
                })}
              </div>
            </div>
          ))
        )}
      </div>

      {/* Legend */}
      <div className="cal-picker__legend">
        <span className="cal-picker__legend-item"><span className="cal-picker__legend-swatch cal-picker__legend-swatch--available" /> Available</span>
        <span className="cal-picker__legend-item"><span className="cal-picker__legend-swatch cal-picker__legend-swatch--before-eta" /> Before ETA</span>
        <span className="cal-picker__legend-item"><span className="cal-picker__legend-swatch cal-picker__legend-swatch--blocked" /> Blocked</span>
        <span className="cal-picker__legend-item"><span className="cal-picker__legend-swatch cal-picker__legend-swatch--selected" /> Selected</span>
      </div>
    </div>
  );
}

function fmtShortTime(iso: string): string {
  try {
    return new Date(iso).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", hour12: true });
  } catch { return iso; }
}

function fmtShortDate(iso: string): string {
  try {
    return new Date(iso).toLocaleDateString("en-IN", { day: "2-digit", month: "short" });
  } catch { return iso; }
}

function fmtDateTab(date: string): string {
  try {
    const d = new Date(date + "T00:00:00");
    const day = d.toLocaleDateString("en-IN", { weekday: "short" });
    const num = d.toLocaleDateString("en-IN", { day: "2-digit", month: "short" });
    return `${day} ${num}`;
  } catch { return date; }
}

function fmtHour(iso: string): string {
  try {
    const d = new Date(iso);
    const h = d.getHours();
    return h < 12 ? `${h || 12}a` : `${h === 12 ? 12 : h - 12}p`;
  } catch { return ""; }
}

function getScoreClass(score: number): string {
  if (score >= 80) return "high";
  if (score >= 60) return "medium";
  if (score >= 40) return "low";
  return "poor";
}

export default SlotCalendarPicker;
