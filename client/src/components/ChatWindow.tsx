import { useEffect, useRef } from "react";
import MessageBubble from "./MessageBubble";
import type { Message } from "../types/chat";

interface ChatWindowProps {
  messages: Message[];
  isLoading: boolean;
}

function ChatWindow({ messages, isLoading }: ChatWindowProps) {
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
              width="48"
              height="48"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.5"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z" />
            </svg>
          </div>
          <h2>Welcome, Driver</h2>
          <p>
            Report your issue, delay, or en-route problem here. I will collect
            the details and alert operations.
          </p>
          <div className="chat-window__hints">
            <span>Try: &quot;DRV014, SHP1014, VEH014. Late by 70 min. ETA 11:25. Jaipur DC.&quot;</span>
          </div>
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
