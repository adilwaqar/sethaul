import { useState, useCallback } from "react";
import LoginScreen from "./components/LoginScreen";
import ChatScreen from "./components/ChatScreen";
import type { DriverProfile } from "./types/chat";

function App() {
  const [driver, setDriver] = useState<DriverProfile | null>(null);

  const handleLogin = useCallback((profile: DriverProfile) => {
    setDriver(profile);
  }, []);

  const handleLogout = useCallback(() => {
    setDriver(null);
    localStorage.removeItem("sethaul_driver");
  }, []);

  // If not logged in, show login screen
  if (!driver) {
    return <LoginScreen onLogin={handleLogin} />;
  }

  // Otherwise show chat
  return <ChatScreen driver={driver} onLogout={handleLogout} />;
}

export default App;
