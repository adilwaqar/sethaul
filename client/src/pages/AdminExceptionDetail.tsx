import { useState, useEffect } from "react";
import { useParams, useNavigate } from "react-router-dom";
import SlotCalendarPicker from "../components/SlotCalendarPicker";
import {
  fetchExceptionDetail,
  fetchSuggestions,
  approveException,
  escalateException,
  fetchAvailableSlots,
  type SlotSuggestion,
  type SuggestionResponse,
  type AvailableSlot,
} from "../services/adminApi";

function AdminExceptionDetail() {
  const { exceptionId } = useParams<{ exceptionId: string }>();
  const navigate = useNavigate();

  const [detail, setDetail] = useState<Record<string, unknown> | null>(null);
  const [suggestions, setSuggestions] = useState<SuggestionResponse | null>(null);
  const [calendarSlots, setCalendarSlots] = useState<AvailableSlot[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionLoading, setActionLoading] = useState(false);
  const [selectedSlot, setSelectedSlot] = useState<string>("");
  const [notes, setNotes] = useState("");
  const [escalateReason, setEscalateReason] = useState("");
  const [actionResult, setActionResult] = useState<string | null>(null);

  useEffect(() => {
    if (!exceptionId) return;
    loadAll();
  }, [exceptionId]);

  async function loadAll() {
    setLoading(true);
    setError(null);
    try {
      const [detailData, suggData] = await Promise.all([
        fetchExceptionDetail(exceptionId!),
        fetchSuggestions(exceptionId!),
      ]);
      setDetail(detailData);
      setSuggestions(suggData);

      // Load all calendar slots (including before ETA and blocked) for the calendar view
      if (suggData.facility_id && suggData.declared_eta) {
        const calData = await fetchAvailableSlots(
          suggData.facility_id,
          suggData.required_dock_type !== "ANY" ? suggData.required_dock_type : undefined,
          suggData.declared_eta,
          true,
        );
        setCalendarSlots(calData.slots || []);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load data");
    } finally {
      setLoading(false);
    }
  }

  async function handleApprove() {
    if (!selectedSlot || !exceptionId) return;
    setActionLoading(true);
    setError(null);
    try {
      const result = await approveException(exceptionId, selectedSlot, notes || undefined);
      setActionResult(`Approved! Appointment ${result.appointment_id} created.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Approve failed");
    } finally {
      setActionLoading(false);
    }
  }

  async function handleEscalate() {
    if (!escalateReason.trim() || !exceptionId) return;
    setActionLoading(true);
    setError(null);
    try {
      await escalateException(exceptionId, escalateReason);
      setActionResult("Exception escalated successfully.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Escalate failed");
    } finally {
      setActionLoading(false);
    }
  }

  if (loading) {
    return <div className="admin admin--loading"><p>Loading exception details...</p></div>;
  }

  const exc = detail?.exception as Record<string, unknown> | undefined;
  const shipment = detail?.shipment as Record<string, unknown> | undefined;
  const driver = detail?.driver as Record<string, unknown> | undefined;

  return (
    <div className="admin">
      <header className="admin__header">
        <button className="admin__back-btn" onClick={() => navigate("/admin")}>
          &larr; Back to Dashboard
        </button>
        <h1>Exception: {exceptionId}</h1>
      </header>

      {error && <div className="admin__error">{error}</div>}
      {actionResult && <div className="admin__success">{actionResult}</div>}

      {/* Exception Summary */}
      {exc && (
        <div className="detail__grid">
          <div className="detail__card">
            <h3>Exception Info</h3>
            <dl className="detail__dl">
              <dt>Type</dt><dd>{exc.exception_type as string}</dd>
              <dt>Severity</dt>
              <dd>
                <span className={`badge badge--${(exc.severity_code as string).toLowerCase()}`}>
                  {exc.severity_code as string}
                </span>
              </dd>
              <dt>Status</dt><dd>{exc.exception_status as string}</dd>
              <dt>Reported</dt><dd>{formatDateTime(exc.reported_at as string)}</dd>
              <dt>Delay</dt><dd>{exc.reported_delay_min as number ?? "—"} min</dd>
              <dt>Driver ETA</dt><dd>{formatDateTime(exc.declared_eta_ts as string)}</dd>
              <dt>Description</dt><dd>{exc.description as string}</dd>
            </dl>
          </div>

          {driver && (
            <div className="detail__card">
              <h3>Driver</h3>
              <dl className="detail__dl">
                <dt>Name</dt><dd>{driver.driver_name as string}</dd>
                <dt>ID</dt><dd>{driver.driver_id as string}</dd>
                <dt>Phone</dt><dd>{driver.phone as string}</dd>
              </dl>
            </div>
          )}

          {shipment && (
            <div className="detail__card">
              <h3>Shipment</h3>
              <dl className="detail__dl">
                <dt>ID</dt><dd>{shipment.shipment_id as string}</dd>
                <dt>Customer</dt><dd>{shipment.customer_name as string}</dd>
                <dt>Product</dt><dd>{shipment.product_category as string}</dd>
                <dt>Priority</dt>
                <dd>
                  <span className={`badge badge--${(shipment.priority_code as string).toLowerCase()}`}>
                    {shipment.priority_code as string}
                  </span>
                </dd>
                <dt>Dock Type</dt><dd>{shipment.required_dock_type as string}</dd>
                <dt>Weight</dt><dd>{(shipment.load_weight_kg as number).toLocaleString()} kg</dd>
                <dt>Original ETA</dt><dd>{formatDateTime(shipment.original_eta_ts as string)}</dd>
                <dt>Latest ETA</dt><dd>{formatDateTime(shipment.latest_eta_ts as string)}</dd>
                <dt>Status</dt><dd>{shipment.current_status as string}</dd>
                <dt>Unload Time</dt><dd>{shipment.expected_unload_min as number} min</dd>
              </dl>
            </div>
          )}
        </div>
      )}

      {/* Slot Suggestions */}
      {suggestions && !actionResult && (
        <div className="detail__section">
          <h2>Available Slot Options</h2>
          <SlotCalendarPicker
            slots={calendarSlots.map((s) => ({
              slot_id: s.slot_id,
              dock_code: s.dock_code,
              dock_type: s.dock_type,
              slot_start_ts: s.slot_start_ts,
              slot_end_ts: s.slot_end_ts,
              max_vehicle_weight_kg: s.max_vehicle_weight_kg,
              supports_refrigerated: s.supports_refrigerated,
              availability_status: s.availability_status,
              score: suggestions.suggestions.find((ss: SlotSuggestion) => ss.slot_id === s.slot_id)?.score,
              recommendation: suggestions.suggestions.find((ss: SlotSuggestion) => ss.slot_id === s.slot_id)?.recommendation,
            }))}
            selectedSlot={selectedSlot}
            onSelect={setSelectedSlot}
            declaredEta={suggestions.declared_eta}
          />

          {/* Approve Action */}
          {suggestions.suggestions.length > 0 && (
            <div className="detail__actions">
              <div className="detail__action-group">
                <h3>Approve &amp; Assign Slot</h3>
                <textarea
                  className="detail__textarea"
                  placeholder="Operations notes (optional)..."
                  value={notes}
                  onChange={(e) => setNotes(e.target.value)}
                  rows={2}
                />
                <button
                  className="detail__approve-btn"
                  onClick={handleApprove}
                  disabled={!selectedSlot || actionLoading}
                >
                  {actionLoading ? "Processing..." : `Approve Slot ${selectedSlot || "(select one)"}`}
                </button>
              </div>
            </div>
          )}

          {/* Escalate Action */}
          <div className="detail__actions">
            <div className="detail__action-group detail__action-group--escalate">
              <h3>Escalate (No Feasible Slot)</h3>
              <textarea
                className="detail__textarea"
                placeholder="Reason for escalation..."
                value={escalateReason}
                onChange={(e) => setEscalateReason(e.target.value)}
                rows={2}
              />
              <button
                className="detail__escalate-btn"
                onClick={handleEscalate}
                disabled={!escalateReason.trim() || actionLoading}
              >
                {actionLoading ? "Processing..." : "Escalate"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  try {
    const d = new Date(iso);
    return d.toLocaleString("en-IN", {
      day: "2-digit",
      month: "short",
      hour: "2-digit",
      minute: "2-digit",
      hour12: true,
    });
  } catch {
    return iso;
  }
}

export default AdminExceptionDetail;
