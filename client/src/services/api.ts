import type { ChatRequest, ChatResponse } from "../types/chat";

const API_BASE_URL = import.meta.env.VITE_API_URL || "/api";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface LoginRequest {
  phone: string;
}

export interface LoginResponse {
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

export interface SessionInfo {
  session_id: string;
  driver_id: string;
  shipment_id: string | null;
  thread_status: string;
  thread_intent: string;
  opened_at: string;
  messages: Array<{
    chat_message_id: string;
    sender_type: string;
    message_text: string;
    message_ts: string;
  }>;
}

export interface NewSessionResponse {
  session_id: string;
  driver_id: string;
}

// ---------------------------------------------------------------------------
// Auth
// ---------------------------------------------------------------------------

/**
 * Authenticate a driver by phone number.
 * Returns driver profile and their last open session (if any).
 */
export async function loginDriver(phone: string): Promise<LoginResponse> {
  const response = await fetch(`${API_BASE_URL}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ phone: phone.trim() }),
  });

  if (!response.ok) {
    const err = await response.json().catch(() => ({ detail: "Login failed" }));
    throw new Error(err.detail || `Login failed (${response.status})`);
  }

  return response.json();
}

// ---------------------------------------------------------------------------
// Sessions
// ---------------------------------------------------------------------------

/**
 * Create a new chat session for a driver.
 */
export async function createNewSession(driverId: string): Promise<NewSessionResponse> {
  const response = await fetch(`${API_BASE_URL}/sessions/new?driver_id=${driverId}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
  });

  if (!response.ok) {
    const err = await response.json().catch(() => ({ detail: "Failed to create session" }));
    throw new Error(err.detail || `Session creation failed (${response.status})`);
  }

  return response.json();
}

/**
 * Get session details and message history for resumption.
 */
export async function getSession(sessionId: string): Promise<SessionInfo> {
  const response = await fetch(`${API_BASE_URL}/sessions/${sessionId}`);

  if (!response.ok) {
    const err = await response.json().catch(() => ({ detail: "Session not found" }));
    throw new Error(err.detail || `Session fetch failed (${response.status})`);
  }

  return response.json();
}

// ---------------------------------------------------------------------------
// Chat
// ---------------------------------------------------------------------------

/**
 * Send a driver message to the agent and get a response.
 */
export async function sendMessage(
  prompt: string,
  sessionId: string,
  driverId: string,
  shipmentId: string
): Promise<ChatResponse> {
  const body: ChatRequest = {
    prompt: prompt.trim(),
    session_id: sessionId,
    driver_id: driverId,
    shipment_id: shipmentId,
  };

  const response = await fetch(`${API_BASE_URL}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

  if (!response.ok) {
    const errorText = await response.text().catch(() => "Unknown error");
    throw new Error(`Server error (${response.status}): ${errorText}`);
  }

  const data: ChatResponse = await response.json();

  if (data.error) {
    throw new Error(data.error);
  }

  return data;
}
