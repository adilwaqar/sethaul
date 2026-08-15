import { useState, useEffect, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import SlotCalendarPicker from "../components/SlotCalendarPicker";
import {
  fetchShipmentFormData,
  fetchAvailableSlots,
  createShipment,
  type ShipmentFormData,
  type AvailableSlot,
  type CreateShipmentPayload,
} from "../services/adminApi";

function AdminCreateShipment() {
  const navigate = useNavigate();

  const [formData, setFormData] = useState<ShipmentFormData | null>(null);
  const [slots, setSlots] = useState<AvailableSlot[]>([]);
  const [slotsLoading, setSlotsLoading] = useState(false);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  // Form fields
  const [carrierId, setCarrierId] = useState("");
  const [driverId, setDriverId] = useState("");
  const [vehicleId, setVehicleId] = useState("");
  const [facilityId, setFacilityId] = useState("");
  const [originName, setOriginName] = useState("");
  const [originCity, setOriginCity] = useState("");
  const [customerName, setCustomerName] = useState("");
  const [productCategory, setProductCategory] = useState("");
  const [loadWeight, setLoadWeight] = useState<number>(10000);
  const [palletCount, setPalletCount] = useState<number>(20);
  const [dockType, setDockType] = useState("STANDARD");
  const [tempControl, setTempControl] = useState(false);
  const [priority, setPriority] = useState("NORMAL");
  const [departureDt, setDepartureDt] = useState("");
  const [etaDt, setEtaDt] = useState("");
  const [unloadMin, setUnloadMin] = useState(60);
  const [selectedSlots, setSelectedSlots] = useState<string[]>([]);

  // Load form reference data
  useEffect(() => {
    fetchShipmentFormData()
      .then(setFormData)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, []);

  // Filter drivers by carrier
  const filteredDrivers = useMemo(() => {
    if (!formData || !carrierId) return formData?.drivers || [];
    return formData.drivers.filter((d) => d.carrier_id === carrierId);
  }, [formData, carrierId]);

  // Filter vehicles by carrier
  const filteredVehicles = useMemo(() => {
    if (!formData || !carrierId) return formData?.vehicles || [];
    return formData.vehicles.filter((v) => v.carrier_id === carrierId);
  }, [formData, carrierId]);

  // Auto-determine dock type from vehicle/weight
  useEffect(() => {
    if (loadWeight > 25000) {
      setDockType("HEAVY");
    } else if (tempControl) {
      setDockType("REEFER");
    }
  }, [loadWeight, tempControl]);

  // Load available slots when facility, dock type, or ETA changes
  useEffect(() => {
    if (!facilityId || !etaDt) {
      setSlots([]);
      return;
    }
    setSlotsLoading(true);
    const isoEta = toIso(etaDt);
    fetchAvailableSlots(facilityId, dockType !== "ANY" ? dockType : undefined, isoEta, true)
      .then((res) => setSlots(res.slots || []))
      .catch(() => setSlots([]))
      .finally(() => setSlotsLoading(false));
  }, [facilityId, dockType, etaDt]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSuccess(null);

    if (selectedSlots.length === 0) {
      setError("Please select at least one appointment slot.");
      return;
    }

    const payload: CreateShipmentPayload = {
      carrier_id: carrierId,
      driver_id: driverId,
      vehicle_id: vehicleId,
      origin_name: originName,
      origin_city: originCity,
      destination_facility_id: facilityId,
      customer_name: customerName,
      product_category: productCategory,
      load_weight_kg: loadWeight,
      pallet_count: palletCount || null,
      required_dock_type: dockType,
      temperature_control_required: tempControl,
      priority_code: priority,
      planned_departure_ts: toIso(departureDt),
      original_eta_ts: toIso(etaDt),
      expected_unload_min: unloadMin,
      slot_id: selectedSlots[0],
      slot_ids: selectedSlots,
    };

    setSubmitting(true);
    try {
      const result = await createShipment(payload);
      setSuccess(
        `Shipment ${result.shipment_id} created! Order: ${result.order_reference}, ` +
        `Appointment: ${result.appointment_id}`
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Creation failed");
    } finally {
      setSubmitting(false);
    }
  }

  if (loading) {
    return <div className="admin admin--loading"><p>Loading form data...</p></div>;
  }

  return (
    <div className="admin">
      <header className="admin__header">
        <button className="admin__back-btn" onClick={() => navigate("/admin")}>
          &larr; Back to Dashboard
        </button>
        <h1>Create New Shipment</h1>
      </header>

      {error && <div className="admin__error">{error}</div>}
      {success && <div className="admin__success">{success}</div>}

      {!success && (
        <form className="shipment-form" onSubmit={handleSubmit}>
          {/* --- Carrier & Assignment --- */}
          <fieldset className="shipment-form__section">
            <legend>Carrier &amp; Assignment</legend>
            <div className="shipment-form__grid">
              <div className="form-field">
                <label>Carrier *</label>
                <select value={carrierId} onChange={(e) => { setCarrierId(e.target.value); setDriverId(""); setVehicleId(""); }} required>
                  <option value="">Select carrier</option>
                  {formData?.carriers.map((c) => (
                    <option key={c.carrier_id} value={c.carrier_id}>{c.carrier_name}</option>
                  ))}
                </select>
              </div>

              <div className="form-field">
                <label>Driver *</label>
                <select value={driverId} onChange={(e) => setDriverId(e.target.value)} required disabled={!carrierId}>
                  <option value="">Select driver</option>
                  {filteredDrivers.map((d) => (
                    <option key={d.driver_id} value={d.driver_id}>
                      {d.driver_name} ({d.driver_id})
                    </option>
                  ))}
                </select>
              </div>

              <div className="form-field">
                <label>Vehicle *</label>
                <select value={vehicleId} onChange={(e) => setVehicleId(e.target.value)} required disabled={!carrierId}>
                  <option value="">Select vehicle</option>
                  {filteredVehicles.map((v) => (
                    <option key={v.vehicle_id} value={v.vehicle_id}>
                      {v.registration_number} — {v.vehicle_types?.description || v.vehicle_type_code} ({v.capacity_kg.toLocaleString()} kg)
                    </option>
                  ))}
                </select>
              </div>
            </div>
          </fieldset>

          {/* --- Origin & Destination --- */}
          <fieldset className="shipment-form__section">
            <legend>Origin &amp; Destination</legend>
            <div className="shipment-form__grid">
              <div className="form-field">
                <label>Origin Name *</label>
                <input type="text" value={originName} onChange={(e) => setOriginName(e.target.value)} placeholder="e.g. Neemrana Auto Components" required />
              </div>
              <div className="form-field">
                <label>Origin City *</label>
                <input type="text" value={originCity} onChange={(e) => setOriginCity(e.target.value)} placeholder="e.g. Neemrana" required />
              </div>
              <div className="form-field">
                <label>Destination Facility *</label>
                <select value={facilityId} onChange={(e) => setFacilityId(e.target.value)} required>
                  <option value="">Select facility</option>
                  {formData?.facilities.map((f) => (
                    <option key={f.facility_id} value={f.facility_id}>
                      {f.facility_name} ({f.city})
                    </option>
                  ))}
                </select>
              </div>
            </div>
          </fieldset>

          {/* --- Cargo Details --- */}
          <fieldset className="shipment-form__section">
            <legend>Cargo Details</legend>
            <div className="shipment-form__grid">
              <div className="form-field">
                <label>Customer Name *</label>
                <input type="text" value={customerName} onChange={(e) => setCustomerName(e.target.value)} placeholder="e.g. RajRetail Distribution" required />
              </div>
              <div className="form-field">
                <label>Product Category *</label>
                <input type="text" value={productCategory} onChange={(e) => setProductCategory(e.target.value)} placeholder="e.g. Auto components" required />
              </div>
              <div className="form-field">
                <label>Load Weight (kg) *</label>
                <input type="number" value={loadWeight} onChange={(e) => setLoadWeight(Number(e.target.value))} min={1} required />
              </div>
              <div className="form-field">
                <label>Pallet Count</label>
                <input type="number" value={palletCount} onChange={(e) => setPalletCount(Number(e.target.value))} min={0} />
              </div>
              <div className="form-field">
                <label>Dock Type *</label>
                <select value={dockType} onChange={(e) => setDockType(e.target.value)}>
                  <option value="STANDARD">STANDARD</option>
                  <option value="REEFER">REEFER</option>
                  <option value="HEAVY">HEAVY</option>
                  <option value="ANY">ANY</option>
                </select>
              </div>
              <div className="form-field">
                <label>Priority *</label>
                <select value={priority} onChange={(e) => setPriority(e.target.value)}>
                  <option value="LOW">LOW</option>
                  <option value="NORMAL">NORMAL</option>
                  <option value="HIGH">HIGH</option>
                  <option value="CRITICAL">CRITICAL</option>
                </select>
              </div>
              <div className="form-field form-field--checkbox">
                <label>
                  <input type="checkbox" checked={tempControl} onChange={(e) => setTempControl(e.target.checked)} />
                  Temperature Control Required
                </label>
              </div>
              <div className="form-field">
                <label>Expected Unload (min) *</label>
                <input type="number" value={unloadMin} onChange={(e) => setUnloadMin(Number(e.target.value))} min={15} max={180} required />
              </div>
            </div>
          </fieldset>

          {/* --- Schedule --- */}
          <fieldset className="shipment-form__section">
            <legend>Schedule</legend>
            <div className="shipment-form__grid">
              <div className="form-field">
                <label>Planned Departure *</label>
                <input type="datetime-local" value={departureDt} onChange={(e) => setDepartureDt(e.target.value)} required />
              </div>
              <div className="form-field">
                <label>Expected Arrival (ETA) *</label>
                <input type="datetime-local" value={etaDt} onChange={(e) => setEtaDt(e.target.value)} required />
              </div>
            </div>
          </fieldset>

          {/* --- Slot Selection --- */}
          <fieldset className="shipment-form__section">
            <legend>Appointment Slot</legend>
            {!facilityId || !etaDt ? (
              <p className="detail__empty">Select a facility and ETA to see available slots.</p>
            ) : (
              <SlotCalendarPicker
                slots={slots}
                selectedSlots={selectedSlots}
                onSelectSlots={setSelectedSlots}
                declaredEta={toIso(etaDt)}
                loading={slotsLoading}
                maxSlots={3}
              />
            )}
          </fieldset>

          <div className="shipment-form__actions">
            <button type="submit" className="detail__approve-btn" disabled={submitting || selectedSlots.length === 0}>
              {submitting ? "Creating..." : `Create Shipment & Assign ${selectedSlots.length} Slot${selectedSlots.length > 1 ? "s" : ""}`}
            </button>
          </div>
        </form>
      )}
    </div>
  );
}

function toIso(localDt: string): string {
  if (!localDt) return "";
  // Convert "2026-08-04T08:00" → "2026-08-04T08:00:00+05:30"
  return `${localDt}:00+05:30`;
}

export default AdminCreateShipment;
