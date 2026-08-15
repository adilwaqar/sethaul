import { useState } from "react";
import { loginDriver } from "../services/api";
import type { DriverProfile } from "../types/chat";

interface LoginScreenProps {
  onLogin: (profile: DriverProfile) => void;
}

function LoginScreen({ onLogin }: LoginScreenProps) {
  const [phone, setPhone] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    const trimmed = phone.trim();
    if (!trimmed) {
      setError("Please enter your phone number.");
      return;
    }

    setIsLoading(true);
    try {
      const response = await loginDriver(trimmed);
      const profile: DriverProfile = {
        driver_id: response.driver_id,
        driver_name: response.driver_name,
        phone: response.phone,
        carrier_id: response.carrier_id,
        home_base_city: response.home_base_city,
        active_sessions: response.active_sessions,
      };
      // Persist login state
      localStorage.setItem("sethaul_driver", JSON.stringify(profile));
      onLogin(profile);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed.");
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="login-screen">
      <div className="login-card">
        <div className="login-card__header">
          <div className="login-card__icon">
            <svg
              width="32"
              height="32"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z" />
            </svg>
          </div>
          <h1>SetuHaul Driver</h1>
          <p>Enter your registered phone number to start</p>
        </div>

        <form className="login-card__form" onSubmit={handleSubmit}>
          <label htmlFor="phone-input" className="login-card__label">
            Phone Number
          </label>
          <input
            id="phone-input"
            type="tel"
            className="login-card__input"
            placeholder="+91-9000010014"
            value={phone}
            onChange={(e) => setPhone(e.target.value)}
            disabled={isLoading}
            autoFocus
          />

          {error && <p className="login-card__error">{error}</p>}

          <button
            type="submit"
            className="login-card__button"
            disabled={isLoading || !phone.trim()}
          >
            {isLoading ? "Logging in..." : "Continue"}
          </button>
        </form>
      </div>
    </div>
  );
}

export default LoginScreen;
