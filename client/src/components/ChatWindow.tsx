import { useEffect, useRef } from "react";
import MessageBubble from "./MessageBubble";
import type { Message } from "../types/chat";

interface ChatWindowProps {
  messages: Message[];
  isLoading: boolean;
  onSuggestion?: (text: string) => void;
  driverName?: string;
}

const SUGGESTIONS = [
  "Stuck in traffic near Shahpura. I'll reach around 15:40 — my slot at Jaipur DC will be missed.",
  "Tyre burst on NH48, repaired now. Running about 70 minutes late, new ETA 16:20. This load is urgent.",
  "Reached the gate early — can I get a dock now instead of waiting for my slot?",
];

function ChatWindow({ messages, isLoading, onSuggestion, driverName }: ChatWindowProps) {
  const firstName = driverName?.trim().split(/\s+/)[0];
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isLoading]);

  return (
    <main className="chat-window">
      {messages.length === 0 && !isLoading && (
        <div className="chat-window__empty">
          <div className="chat-window__empty-icon">
            <svg
              width="40"
              height="40"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.6"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <path d="M14 17H2V6a1 1 0 0 1 1-1h10a1 1 0 0 1 1 1v11z" />
              <path d="M14 9h4l3 4v4h-7V9z" />
              <circle cx="6" cy="19" r="2" />
              <circle cx="17.5" cy="19" r="2" />
            </svg>
          </div>
          <h2>Namaste, {firstName || "Driver"}</h2>
          <p>
            Tell me what happened on the road — a delay, breakdown, or early
            arrival. I&apos;ll collect the details and alert the operations team
            right away.
          </p>
          {onSuggestion ? (
            <div className="chat-window__suggestions">
              {SUGGESTIONS.map((s) => (
                <button
                  key={s}
                  type="button"
                  className="suggestion-chip"
                  onClick={() => onSuggestion(s)}
                >
                  {s}
                </button>
              ))}
            </div>
          ) : (
            <div className="chat-window__hints">
              <span>Select a shipment above to begin.</span>
            </div>
          )}
        </div>
      )}

      {messages.map((msg) => (
        <MessageBubble key={msg.id} message={msg} />
      ))}

      {isLoading && (
        <div className="chat-window__typing">
          <div className="typing-indicator">
            <span></span>
            <span></span>
            <span></span>
          </div>
        </div>
      )}

      <div ref={bottomRef} />
    </main>
  );
}

export default ChatWindow;
