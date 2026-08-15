interface ChatHeaderProps {
  sessionId: string;
  driverName: string;
  onNewSession: () => void;
  onLogout: () => void;
}

function ChatHeader({ sessionId, driverName, onNewSession, onLogout }: ChatHeaderProps) {
  return (
    <header className="chat-header">
      <div className="chat-header__left">
        <div className="chat-header__icon">
          <svg
            width="24"
            height="24"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <rect x="1" y="3" width="15" height="13" rx="2" />
            <path d="M16 8h4a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2v-4" />
          </svg>
        </div>
        <div className="chat-header__info">
          <h1>SetuHaul Driver Assist</h1>
          <span className="chat-header__session">
            {driverName} &middot; {sessionId ? sessionId.slice(0, 12) + "..." : "initializing..."}
          </span>
        </div>
      </div>
      <div className="chat-header__actions">
        <button className="chat-header__new-btn" onClick={onNewSession}>
          New Issue
        </button>
        <button className="chat-header__logout-btn" onClick={onLogout}>
          Logout
        </button>
      </div>
    </header>
  );
}

export default ChatHeader;
