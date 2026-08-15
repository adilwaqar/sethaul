const SESSION_KEY = "sethaul_session_id";

/**
 * Generates a unique session ID using crypto.randomUUID().
 * Format: "drv-<uuid>" to identify driver sessions.
 */
function generateSessionId(): string {
  const uuid = crypto.randomUUID();
  return `drv-${uuid}`;
}

/**
 * Retrieves the current session ID from localStorage.
 * If none exists, generates a new one and persists it.
 */
export function getSessionId(): string {
  const stored = localStorage.getItem(SESSION_KEY);

  if (stored) {
    return stored;
  }

  const newId = generateSessionId();
  localStorage.setItem(SESSION_KEY, newId);
  return newId;
}

/**
 * Clears the current session, forcing a new one on next call.
 */
export function clearSession(): void {
  localStorage.removeItem(SESSION_KEY);
}
