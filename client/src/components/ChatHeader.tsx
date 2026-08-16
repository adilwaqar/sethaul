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
            strokeWidth="1.8"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <path d="M14 17H2V6a1 1 0 0 1 1-1h10a1 1 0 0 1 1 1v11z" />
            <path d="M14 9h4l3 4v4h-7V9z" />
            <circle cx="6" cy="19" r="2" />
            <circle cx="17.5" cy="19" r="2" />
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
