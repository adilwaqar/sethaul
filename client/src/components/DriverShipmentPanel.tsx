import { useState, useEffect } from "react";

const API_BASE_URL = import.meta.env.VITE_API_URL || "/api";

interface ShipmentContext {
  shipment_id: string;
  order_reference: string;
  origin_name: string;
  origin_city: string;
  destination_facility_id: string;
  customer_name: string;
  product_category: string;
  load_weight_kg: number;
  required_dock_type: string;
  priority_code: string;
  planned_departure_ts: string;
  actual_departure_ts: string;
  original_eta_ts: string;
  latest_eta_ts: string;
  current_status: string;
  facilities?: { facility_name: string; city: string };
  vehicles?: { registration_number: string; vehicle_type_code: string };
  latest_exception: {
    exception_id: string;
    exception_type: string;
    severity_code: string;
    exception_status: string;
    declared_eta_ts: string | null;
    description: string;
  } | null;
  latest_eta_update: {
    source_type: string;
    declared_eta_ts: string;
    confidence_code: string;
    delay_reason_code: string | null;
    note: string | null;
  } | null;
  current_appointment: {
    appointment_id: string;
    appointment_status: string;
    appointment_slots?: { slot_start_ts: string; slot_end_ts: string };
  } | null;
  eta_approval_status: "PENDING_APPROVAL" | "APPROVED" | "ESCALATED" | null;
}

interface DriverShipmentPanelProps {
  driverId: string;
  collapsed: boolean;
}

function DriverShipmentPanel({ driverId, collapsed }: DriverShipmentPanelProps) {
  const [shipments, setShipments] = useState<ShipmentContext[]>([]);
  const [loading, setLoading] = useState(true);

  function loadData() {
    if (!driverId) return;
    setLoading(true);
    fetch(`${API_BASE_URL}/drivers/${driverId}/context`)
      .then((r) => r.json())
      .then((data) => setShipments(data.shipments || []))
      .catch(() => setShipments([]))
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    if (!driverId || collapsed) return;
    loadData();
  }, [driverId, collapsed]);

  if (collapsed) return null;

  return (
    <div className="driver-panel">
      <div className="driver-panel__header-row">
        <p className="driver-panel__header">My Shipments</p>
        <button className="driver-panel__refresh" onClick={loadData} disabled={loading} title="Refresh">
          ↻
        </button>
      </div>

      {loading && <p className="driver-panel__empty">Loading...</p>}

      {!loading && shipments.length === 0 && (
        <p className="driver-panel__empty">No active shipments assigned.</p>
      )}

      {!loading &&
        shipments.map((s) => (
          <div key={s.shipment_id} className="driver-panel__shipment">
            <div className="driver-panel__shipment-header">
              <span className={`badge badge--${s.current_status.toLowerCase()}`}>
                {s.current_status.replace(/_/g, " ")}
              </span>
              <span className="driver-panel__shipment-id">{s.shipment_id}</span>
            </div>

            <div className="driver-panel__field">
              <span className="driver-panel__field-label">Origin</span>
              <span className="driver-panel__field-value">{s.origin_name}, {s.origin_city}</span>
            </div>
            <div className="driver-panel__field">
              <span className="driver-panel__field-label">Destination</span>
              <span className="driver-panel__field-value">
                {s.facilities?.facility_name || s.destination_facility_id}
              </span>
            </div>
            <div className="driver-panel__field">
              <span className="driver-panel__field-label">Customer</span>
              <span className="driver-panel__field-value">{s.customer_name}</span>
            </div>
            <div className="driver-panel__field">
              <span className="driver-panel__field-label">Product</span>
              <span className="driver-panel__field-value">{s.product_category}</span>
            </div>
            <div className="driver-panel__field">
              <span className="driver-panel__field-label">Priority</span>
              <span className="driver-panel__field-value">
                <span className={`badge badge--${s.priority_code.toLowerCase()}`}>{s.priority_code}</span>
              </span>
            </div>
            <div className="driver-panel__field">
              <span className="driver-panel__field-label">Planned Departure</span>
              <span className="driver-panel__field-value">{fmtTime(s.planned_departure_ts)}</span>
            </div>
            <div className="driver-panel__field">
              <span className="driver-panel__field-label">Actual Departure</span>
              <span className="driver-panel__field-value">{fmtTime(s.actual_departure_ts)}</span>
            </div>
            <div className="driver-panel__field">
              <span className="driver-panel__field-label">Planned ETA</span>
              <span className="driver-panel__field-value">{fmtTime(s.original_eta_ts)}</span>
            </div>
            <div className="driver-panel__field">
              <span className="driver-panel__field-label">Current ETA</span>
              <span className="driver-panel__field-value">{fmtTime(s.latest_eta_ts)}</span>
            </div>

            {s.current_appointment && (
              <div className="driver-panel__field">
                <span className="driver-panel__field-label">Slot</span>
                <span className="driver-panel__field-value">
                  {fmtTime(s.current_appointment.appointment_slots?.slot_start_ts || "")}
                  {" – "}
                  {fmtTime(s.current_appointment.appointment_slots?.slot_end_ts || "")}
                </span>
              </div>
            )}

            {/* ETA Approval Status */}
            {s.eta_approval_status && (
              <div className={`driver-panel__eta-status driver-panel__eta-status--${s.eta_approval_status === "PENDING_APPROVAL" ? "pending" : s.eta_approval_status === "APPROVED" ? "approved" : "escalated"}`}>
                {s.eta_approval_status === "PENDING_APPROVAL" && (
                  <>Requested ETA: {fmtTime(s.latest_exception?.declared_eta_ts || "")} — Approval pending</>
                )}
                {s.eta_approval_status === "APPROVED" && (
                  <>ETA approved: {fmtTime(s.latest_eta_ts)}</>
                )}
                {s.eta_approval_status === "ESCALATED" && (
                  <>Issue escalated — Operations reviewing</>
                )}
              </div>
            )}

            {/* Exception info if any */}
            {s.latest_exception && s.eta_approval_status === null && s.latest_exception.exception_status !== "RESOLVED" && (
              <div className="driver-panel__eta-status driver-panel__eta-status--pending">
                {s.latest_exception.exception_type}: {s.latest_exception.description.slice(0, 80)}
              </div>
            )}
          </div>
        ))}
    </div>
  );
}

function fmtTime(iso: string): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString("en-IN", {
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

export default DriverShipmentPanel;
