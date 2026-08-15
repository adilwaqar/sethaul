const API_BASE_URL = import.meta.env.VITE_API_URL || "/api";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface DashboardSummary {
  total_shipments: number;
  status_breakdown: Record<string, number>;
  active_exceptions: number;
  severity_breakdown: Record<string, number>;
}

export interface ShipmentRow {
  shipment_id: string;
  order_reference: string;
  driver_id: string;
  vehicle_id: string;
  destination_facility_id: string;
  current_status: string;
  priority_code: string;
  original_eta_ts: string;
  latest_eta_ts: string;
  required_dock_type: string;
  load_weight_kg: number;
  expected_unload_min: number;
  customer_name: string;
  product_category: string;
  facilities?: { facility_name: string; city: string };
  drivers?: { driver_name: string; phone: string };
  vehicles?: { registration_number: string; vehicle_type_code: string };
}

export interface ExceptionRow {
  exception_id: string;
  shipment_id: string | null;
  driver_id: string;
  thread_id: string;
  exception_type: string;
  reported_at: string;
  reported_delay_min: number | null;
  declared_eta_ts: string | null;
  severity_code: string;
  exception_status: string;
  description: string;
  shipments?: {
    destination_facility_id: string;
    priority_code: string;
    required_dock_type: string;
    load_weight_kg: number;
    current_status: string;
    customer_name: string;
    product_category: string;
    original_eta_ts: string;
    latest_eta_ts: string;
  };
  drivers?: { driver_name: string; phone: string };
}

export interface DashboardData {
  shipments: ShipmentRow[];
  exceptions: ExceptionRow[];
  summary: DashboardSummary;
  facilities: Array<{ facility_id: string; facility_name: string; city: string }>;
}

export interface SlotSuggestion {
  slot_id: string;
  dock_code: string;
  dock_type: string;
  slot_start: string;
  slot_end: string;
  max_weight_kg: number;
  supports_refrigerated: number;
  score: number;
  recommendation: string;
}

export interface SuggestionResponse {
  exception_id: string;
  shipment_id: string;
  facility_id: string;
  declared_eta: string;
  required_dock_type: string;
  load_weight_kg: number;
  priority_code: string;
  expected_unload_min: number;
  current_appointment: Record<string, unknown> | null;
  suggestions: SlotSuggestion[];
  facility: Record<string, unknown>;
  rules: Array<Record<string, unknown>>;
  compatible_docks: Array<Record<string, unknown>>;
}

export interface FilterOptions {
  facilities: Array<{ facility_id: string; facility_name: string; city: string }>;
  drivers: Array<{ driver_id: string; driver_name: string }>;
  statuses: string[];
  exception_types: string[];
  severities: string[];
}

// ---------------------------------------------------------------------------
// API Calls
// ---------------------------------------------------------------------------

export async function fetchDashboard(params?: {
  facility_id?: string;
  status?: string;
  driver_id?: string;
  exception_type?: string;
}): Promise<DashboardData> {
  const url = new URL(`${API_BASE_URL}/admin/dashboard`, window.location.origin);
  if (params) {
    Object.entries(params).forEach(([k, v]) => {
      if (v) url.searchParams.set(k, v);
    });
  }
  const res = await fetch(url.toString());
  if (!res.ok) throw new Error(`Dashboard fetch failed (${res.status})`);
  return res.json();
}

export async function fetchFilters(): Promise<FilterOptions> {
  const res = await fetch(`${API_BASE_URL}/admin/filters`);
  if (!res.ok) throw new Error(`Filters fetch failed (${res.status})`);
  return res.json();
}

export async function fetchExceptionDetail(exceptionId: string) {
  const res = await fetch(`${API_BASE_URL}/admin/exceptions/${exceptionId}`);
  if (!res.ok) throw new Error(`Exception fetch failed (${res.status})`);
  return res.json();
}

export async function fetchSuggestions(exceptionId: string): Promise<SuggestionResponse> {
  const res = await fetch(`${API_BASE_URL}/admin/suggestions/${exceptionId}`);
  if (!res.ok) throw new Error(`Suggestions fetch failed (${res.status})`);
  return res.json();
}

export async function approveException(
  exceptionId: string,
  slotId: string,
  notes?: string
): Promise<{ status: string; appointment_id: string }> {
  const res = await fetch(`${API_BASE_URL}/admin/exceptions/${exceptionId}/approve`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ slot_id: slotId, notes }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Approve failed" }));
    throw new Error(err.detail || `Approve failed (${res.status})`);
  }
  return res.json();
}

export async function escalateException(
  exceptionId: string,
  reason: string
): Promise<{ status: string }> {
  const res = await fetch(`${API_BASE_URL}/admin/exceptions/${exceptionId}/escalate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ reason }),
  });
  if (!res.ok) throw new Error(`Escalate failed (${res.status})`);
  return res.json();
}


// ---------------------------------------------------------------------------
// Shipment Creation
// ---------------------------------------------------------------------------

export interface ShipmentFormData {
  carriers: Array<{ carrier_id: string; carrier_name: string }>;
  drivers: Array<{
    driver_id: string;
    driver_name: string;
    carrier_id: string;
    phone: string;
    carriers?: { carrier_name: string };
  }>;
  vehicles: Array<{
    vehicle_id: string;
    carrier_id: string;
    registration_number: string;
    vehicle_type_code: string;
    capacity_kg: number;
    refrigeration_capable: number;
    vehicle_types?: { description: string; typical_dock_type: string; refrigerated_flag: number };
  }>;
  facilities: Array<{
    facility_id: string;
    facility_name: string;
    city: string;
    open_time: string;
    close_time: string;
  }>;
  docks: Array<{
    dock_id: string;
    facility_id: string;
    dock_code: string;
    dock_type: string;
    max_vehicle_weight_kg: number;
    supports_refrigerated: number;
  }>;
}

export interface AvailableSlot {
  slot_id: string;
  facility_id: string;
  dock_code: string;
  dock_type: string;
  slot_start_ts: string;
  slot_end_ts: string;
  max_vehicle_weight_kg: number;
  supports_refrigerated: number;
  availability_status: string;
}

export interface CreateShipmentPayload {
  carrier_id: string;
  driver_id: string;
  vehicle_id: string;
  origin_name: string;
  origin_city: string;
  destination_facility_id: string;
  customer_name: string;
  product_category: string;
  load_weight_kg: number;
  pallet_count: number | null;
  required_dock_type: string;
  temperature_control_required: boolean;
  priority_code: string;
  planned_departure_ts: string;
  original_eta_ts: string;
  expected_unload_min: number;
  slot_id: string;
  slot_ids: string[];
}

export async function fetchShipmentFormData(): Promise<ShipmentFormData> {
  const res = await fetch(`${API_BASE_URL}/admin/shipments/form-data`);
  if (!res.ok) throw new Error(`Form data fetch failed (${res.status})`);
  return res.json();
}

export async function fetchAvailableSlots(
  facilityId: string,
  dockType?: string,
  afterTs?: string,
  includeAll?: boolean
): Promise<{ slots: AvailableSlot[] }> {
  const url = new URL(`${API_BASE_URL}/admin/shipments/available-slots`, window.location.origin);
  url.searchParams.set("facility_id", facilityId);
  if (dockType) url.searchParams.set("dock_type", dockType);
  if (afterTs) url.searchParams.set("after_ts", afterTs);
  if (includeAll) url.searchParams.set("include_all", "true");
  const res = await fetch(url.toString());
  if (!res.ok) throw new Error(`Slots fetch failed (${res.status})`);
  return res.json();
}

export async function createShipment(
  payload: CreateShipmentPayload
): Promise<{ status: string; shipment_id: string; appointment_id: string; order_reference: string }> {
  const res = await fetch(`${API_BASE_URL}/admin/shipments/create`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Create failed" }));
    throw new Error(err.detail || `Create failed (${res.status})`);
  }
  return res.json();
}
