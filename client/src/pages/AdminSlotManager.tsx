import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";

const API_BASE_URL = import.meta.env.VITE_API_URL || "/api";

interface Slot {
  slot_id: string;
  facility_id: string;
  dock_id: string;
  slot_start_ts: string;
  slot_end_ts: string;
  slot_status: string;
  block_reason: string | null;
}

interface Facility {
  facility_id: string;
  facility_name: string;
  city: string;
}

function AdminSlotManager() {
  const navigate = useNavigate();

  const [facilities, setFacilities] = useState<Facility[]>([]);
  const [slots, setSlots] = useState<Slot[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  // Filters
  const [facilityId, setFacilityId] = useState("");
  const [dateFilter, setDateFilter] = useState(todayStr());
  const [statusFilter, setStatusFilter] = useState("");

  // Generate form
  const [genStart, setGenStart] = useState(todayStr());
  const [genEnd, setGenEnd] = useState(nextSundayStr());
  const [generating, setGenerating] = useState(false);

  // Bulk select
  const [selectedSlots, setSelectedSlots] = useState<Set<string>>(new Set());

  // Load facilities
  useEffect(() => {
    fetch(`${API_BASE_URL}/admin/filters`)
      .then((r) => r.json())
      .then((d) => {
        setFacilities(d.facilities || []);
        if (d.facilities?.length > 0 && !facilityId) {
          setFacilityId(d.facilities[0].facility_id);
        }
      })
      .catch(() => {});
  }, []);

  // Load slots when filters change
  useEffect(() => {
    if (!facilityId) return;
    loadSlots();
  }, [facilityId, dateFilter, statusFilter]);

  async function loadSlots() {
    setLoading(true);
    setError(null);
    try {
      const url = new URL(`${API_BASE_URL}/admin/slots`, window.location.origin);
      url.searchParams.set("facility_id", facilityId);
      if (dateFilter) url.searchParams.set("date", dateFilter);
      if (statusFilter) url.searchParams.set("status", statusFilter);

      const res = await fetch(url.toString());
      if (!res.ok) throw new Error("Failed to load slots");
      const data = await res.json();
      setSlots(data.slots || []);
      setSelectedSlots(new Set());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Load failed");
    } finally {
      setLoading(false);
    }
  }

  async function handleGenerate() {
    setGenerating(true);
    setError(null);
    setSuccess(null);
    try {
      const res = await fetch(`${API_BASE_URL}/admin/slots/generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ start_date: genStart, end_date: genEnd }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: "Generate failed" }));
        throw new Error(err.detail);
      }
      const data = await res.json();
      setSuccess(`Generated ${data.total_generated} slots, inserted ${data.total_inserted}.`);
      loadSlots();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Generate failed");
    } finally {
      setGenerating(false);
    }
  }

  async function handleUpdateSlot(slotId: string, newStatus: string, reason?: string) {
    try {
      const res = await fetch(`${API_BASE_URL}/admin/slots/${slotId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ slot_status: newStatus, block_reason: reason || null }),
      });
      if (!res.ok) throw new Error("Update failed");
      // Update local state
      setSlots((prev) =>
        prev.map((s) =>
          s.slot_id === slotId
            ? { ...s, slot_status: newStatus, block_reason: reason || null }
            : s
        )
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Update failed");
    }
  }

  async function handleBulkUpdate(newStatus: string) {
    if (selectedSlots.size === 0) return;
    const reason = newStatus === "BLOCKED" ? prompt("Block reason:") || "Blocked by operations" : undefined;

    try {
      const url = new URL(`${API_BASE_URL}/admin/slots/bulk-update`, window.location.origin);
      url.searchParams.set("status", newStatus);
      if (reason) url.searchParams.set("block_reason", reason);

      const res = await fetch(url.toString(), {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(Array.from(selectedSlots)),
      });
      if (!res.ok) throw new Error("Bulk update failed");
      loadSlots();
      setSuccess(`Updated ${selectedSlots.size} slots to ${newStatus}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Bulk update failed");
    }
  }

  function toggleSlotSelection(slotId: string) {
    setSelectedSlots((prev) => {
      const next = new Set(prev);
      if (next.has(slotId)) next.delete(slotId);
      else next.add(slotId);
      return next;
    });
  }

  function toggleSelectAll() {
    if (selectedSlots.size === slots.length) {
      setSelectedSlots(new Set());
    } else {
      setSelectedSlots(new Set(slots.map((s) => s.slot_id)));
    }
  }

  return (
    <div className="admin">
      <header className="admin__header">
        <button className="admin__back-btn" onClick={() => navigate("/admin")}>
          &larr; Dashboard
        </button>
        <h1>Slot Management</h1>
      </header>

      {error && <div className="admin__error">{error}</div>}
      {success && <div className="admin__success">{success}</div>}

      {/* Generate Slots — hidden by default, keep functionality */}
      <div className="detail__card" style={{ marginBottom: 20, display: "none" }}>
        <h3>Generate Weekly Slots</h3>
        <div className="shipment-form__grid" style={{ marginTop: 12 }}>
          <div className="form-field">
            <label>Start Date</label>
            <input type="date" value={genStart} onChange={(e) => setGenStart(e.target.value)} />
          </div>
          <div className="form-field">
            <label>End Date</label>
            <input type="date" value={genEnd} onChange={(e) => setGenEnd(e.target.value)} />
          </div>
          <div className="form-field" style={{ justifyContent: "flex-end" }}>
            <button className="detail__approve-btn" onClick={handleGenerate} disabled={generating}>
              {generating ? "Generating..." : "Generate Slots"}
            </button>
          </div>
        </div>
      </div>

      {/* Filters */}
      <div className="admin__filters">
        <select value={facilityId} onChange={(e) => setFacilityId(e.target.value)}>
          {facilities.map((f) => (
            <option key={f.facility_id} value={f.facility_id}>
              {f.facility_name} ({f.city})
            </option>
          ))}
        </select>
        <input type="date" value={dateFilter} onChange={(e) => setDateFilter(e.target.value)} />
        <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
          <option value="">All Statuses</option>
          <option value="OPEN">OPEN</option>
          <option value="BLOCKED">BLOCKED</option>
          <option value="CLOSED">CLOSED</option>
        </select>
        <button className="admin__refresh" onClick={loadSlots} disabled={loading}>
          {loading ? "Loading..." : "Refresh"}
        </button>
      </div>

      {/* Bulk Actions */}
      {selectedSlots.size > 0 && (
        <div className="slot-bulk-actions">
          <span>{selectedSlots.size} selected</span>
          <button className="detail__approve-btn" onClick={() => handleBulkUpdate("OPEN")}>Set OPEN</button>
          <button className="detail__escalate-btn" onClick={() => handleBulkUpdate("BLOCKED")}>Block</button>
          <button className="admin__action-btn" onClick={() => handleBulkUpdate("CLOSED")}>Close</button>
        </div>
      )}

      {/* Slots Table */}
      <div className="admin__table-wrapper">
        <table className="admin__table">
          <thead>
            <tr>
              <th>
                <input
                  type="checkbox"
                  checked={selectedSlots.size === slots.length && slots.length > 0}
                  onChange={toggleSelectAll}
                />
              </th>
              <th>Slot ID</th>
              <th>Dock</th>
              <th>Start</th>
              <th>End</th>
              <th>Status</th>
              <th>Block Reason</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {slots.length === 0 && (
              <tr><td colSpan={8} className="admin__empty">No slots found. Generate slots above.</td></tr>
            )}
            {slots.map((slot) => (
              <tr key={slot.slot_id} className={selectedSlots.has(slot.slot_id) ? "admin__row--selected" : ""}>
                <td>
                  <input
                    type="checkbox"
                    checked={selectedSlots.has(slot.slot_id)}
                    onChange={() => toggleSlotSelection(slot.slot_id)}
                  />
                </td>
                <td className="admin__mono">{slot.slot_id}</td>
                <td>{slot.dock_id.split("-").pop()}</td>
                <td>{formatTime(slot.slot_start_ts)}</td>
                <td>{formatTime(slot.slot_end_ts)}</td>
                <td>
                  <span className={`badge badge--${slot.slot_status.toLowerCase()}`}>
                    {slot.slot_status}
                  </span>
                </td>
                <td>{slot.block_reason || "—"}</td>
                <td>
                  {slot.slot_status !== "OPEN" && (
                    <button className="slot-action slot-action--open" onClick={() => handleUpdateSlot(slot.slot_id, "OPEN")}>
                      Open
                    </button>
                  )}
                  {slot.slot_status !== "BLOCKED" && (
                    <button className="slot-action slot-action--block" onClick={() => {
                      const reason = prompt("Block reason:") || "Manual block";
                      handleUpdateSlot(slot.slot_id, "BLOCKED", reason);
                    }}>
                      Block
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function todayStr(): string {
  return new Date().toISOString().split("T")[0];
}

function nextSundayStr(): string {
  const now = new Date();
  const daysUntilSunday = 7 - now.getDay();
  const sunday = new Date(now.getTime() + daysUntilSunday * 86400000);
  return sunday.toISOString().split("T")[0];
}

function formatTime(iso: string): string {
  try {
    return new Date(iso).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", hour12: true });
  } catch {
    return iso;
  }
}

export default AdminSlotManager;
