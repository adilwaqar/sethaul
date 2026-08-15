export interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: number;
}

export interface ChatResponse {
  result: string;
  session_id: string;
  error?: string;
}

export interface ChatRequest {
  prompt: string;
  session_id: string;
  driver_id: string;
  shipment_id: string;
}

export interface DriverProfile {
  driver_id: string;
  driver_name: string;
  phone: string;
  carrier_id: string;
  home_base_city: string | null;
  active_sessions?: {
    session_id: string;
    shipment_id: string | null;
    thread_status: string;
    thread_intent: string;
    opened_at: string;
  }[];
}
