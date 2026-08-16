import { useState, useCallback, useRef, useEffect } from "react";
import ChatWindow from "./ChatWindow";
import ChatInput from "./ChatInput";
import ChatHeader from "./ChatHeader";
import DriverShipmentPanel from "./DriverShipmentPanel";
import { sendMessage, createNewSession, getSession } from "../services/api";
import type { Message, DriverProfile } from "../types/chat";

const API_BASE_URL = import.meta.env.VITE_API_URL || "/api";

interface ShipmentOption {
  shipment_id: string;
  order_reference: string;
  origin_name: string;
  origin_city: string;
  destination_facility_id: string;
  customer_name: string;
  current_status: string;
  facilities?: { facility_name: string; city: string };
}

interface ChatScreenProps {
  driver: DriverProfile;
  onLogout: () => void;
}

function ChatScreen({ driver, onLogout }: ChatScreenProps) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sessionId, setSessionId] = useState<string>("");
  const [panelCollapsed, setPanelCollapsed] = useState(false);

  // Shipment selection
  const [shipments, setShipments] = useState<ShipmentOption[]>([]);
  const [selectedShipment, setSelectedShipment] = useState<string>("");
  const [shipmentsLoading, setShipmentsLoading] = useState(true);

  const initialized = useRef(false);

  // Load driver's active shipments for the dropdown
  useEffect(() => {
    fetch(`${API_BASE_URL}/drivers/${driver.driver_id}/shipments`)
      .then((r) => r.json())
      .then((data) => {
        // Filter to non-completed, non-cancelled shipments
        const active = (data.shipments || []).filter(
          (s: ShipmentOption) => !["COMPLETED", "CANCELLED"].includes(s.current_status)
        );
        setShipments(active);
      })
      .catch(() => setShipments([]))
      .finally(() => setShipmentsLoading(false));
  }, [driver.driver_id]);

  // Initialize session — resume active or create new
  useEffect(() => {
    if (initialized.current) return;
    initialized.current = true;

    if (driver.active_sessions?.length) {
      const activeId = driver.active_sessions[0].session_id;
      setSessionId(activeId);

      // Set selected shipment from active session
      if (driver.active_sessions[0].shipment_id) {
        setSelectedShipment(driver.active_sessions[0].shipment_id);
      }

      // Load message history
      getSession(activeId)
        .then((session) => {
          if (session.messages && session.messages.length > 0) {
            const history: Message[] = session.messages.map((msg) => ({
              id: msg.chat_message_id || crypto.randomUUID(),
              role: msg.sender_type === "DRIVER" ? "user" : "assistant",
              content: msg.message_text,
              timestamp: new Date(msg.message_ts).getTime(),
            }));
            setMessages(history);
          }
        })
        .catch((err) => console.warn("Failed to load session history:", err));
    } else {
      createNewSession(driver.driver_id)
        .then((res) => setSessionId(res.session_id))
        .catch((err) => setError(`Failed to create session: ${err.message}`));
    }
  }, [driver]);

  const handleShipmentChange = useCallback(
    async (shipmentId: string) => {
      setSelectedShipment(shipmentId);
      const session = driver.active_sessions?.find((s) => s.shipment_id == shipmentId);
      if (!session) {
        return;
      }
      try {
        getSession(session.session_id)
        .then((session) => {
          if (session.messages && session.messages.length > 0) {
            const history: Message[] = session.messages.map((msg) => ({
              id: msg.chat_message_id || crypto.randomUUID(),
              role: msg.sender_type === "DRIVER" ? "user" : "assistant",
              content: msg.message_text,
              timestamp: new Date(msg.message_ts).getTime(),
            }));
            setMessages(history);
          }
        })
        .catch((err) => console.warn("Failed to load session history:", err));
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to create session");
      }
    },
    []
  );

  const handleSend = useCallback(
    async (text: string) => {
      if (!sessionId || !selectedShipment) return;

      setError(null);

      const userMessage: Message = {
        id: crypto.randomUUID(),
        role: "user",
        content: text,
        timestamp: Date.now(),
      };

      setMessages((prev) => [...prev, userMessage]);
      setIsLoading(true);

      try {
        const response = await sendMessage(text, sessionId, driver.driver_id, selectedShipment);

        const assistantMessage: Message = {
          id: crypto.randomUUID(),
          role: "assistant",
          content: response.result,
          timestamp: Date.now(),
        };

        setMessages((prev) => [...prev, assistantMessage]);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Something went wrong");
      } finally {
        setIsLoading(false);
      }
    },
    [sessionId, selectedShipment, driver.driver_id]
  );

  const handleNewSession = useCallback(async () => {
    try {
      const res = await createNewSession(driver.driver_id);
      setSessionId(res.session_id);
      setMessages([]);
      setSelectedShipment("");
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create session");
    }
  }, [driver.driver_id]);

  const chatDisabled = isLoading || !sessionId || !selectedShipment;
  const placeholderText = !selectedShipment
    ? "Select a shipment to continue..."
    : "Describe your issue (e.g., traffic delay, breakdown, ETA)...";

  return (
    <div className="app">
      <ChatHeader
        sessionId={sessionId}
        driverName={driver.driver_name}
        onNewSession={handleNewSession}
        onLogout={onLogout}
      />

      {/* Shipment Selector Bar */}
      <div className="shipment-selector">
        <label className="shipment-selector__label">Shipment:</label>
        {shipmentsLoading ? (
          <span className="shipment-selector__loading">Loading shipments...</span>
        ) : shipments.length === 0 ? (
          <span className="shipment-selector__empty">No active shipments assigned</span>
        ) : (
          <select
            className="shipment-selector__dropdown"
            value={selectedShipment}
            onChange={(e) => handleShipmentChange(e.target.value)}
          >
            <option value="">-- Select shipment --</option>
            {shipments.map((s) => (
              <option key={s.shipment_id} value={s.shipment_id}>
                {s.shipment_id} — {s.origin_name} → {s.facilities?.facility_name || s.destination_facility_id} ({s.current_status})
              </option>
            ))}
          </select>
        )}
        {selectedShipment && (
          <span className="shipment-selector__active">
            Chatting about: <strong>{selectedShipment}</strong>
          </span>
        )}
      </div>

      <div className="chat-layout">
        <div className="chat-layout__main">
          <ChatWindow
            messages={messages}
            isLoading={isLoading}
            onSuggestion={chatDisabled ? undefined : handleSend}
            driverName={driver.driver_name}
          />
          {error && (
            <div className="error-banner">
              <span>{error}</span>
              <button onClick={() => setError(null)} aria-label="Dismiss error">
                &times;
              </button>
            </div>
          )}
          <ChatInput
            onSend={handleSend}
            disabled={chatDisabled}
            placeholder={placeholderText}
          />
        </div>
        <div className={`chat-layout__panel ${panelCollapsed ? "chat-layout__panel--collapsed" : ""}`}>
          <DriverShipmentPanel driverId={driver.driver_id} collapsed={panelCollapsed} />
        </div>
        <button
          className="panel-toggle"
          onClick={() => setPanelCollapsed((v) => !v)}
          title={panelCollapsed ? "Show shipments" : "Hide shipments"}
        >
          {panelCollapsed ? "◀" : "▶"}
        </button>
      </div>
    </div>
  );
}

export default ChatScreen;
