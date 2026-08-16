import { useState } from "react";
import { loginDriver } from "../services/api";
import type { DriverProfile } from "../types/chat";

interface LoginScreenProps {
  onLogin: (profile: DriverProfile) => void;
}

const DEMO_DRIVERS = [
  { name: "Pradeep Jat", detail: "SHP1014 · critical delay", phone: "+91-9000010014" },
  { name: "Manoj Sharma", detail: "SHP1006 · traffic delay", phone: "+91-9000010006" },
  { name: "Mohammed Salim", detail: "SHP1015 · reefer escalation", phone: "+91-9000010015" },
];

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
              width="34"
              height="34"
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
          <h1>SetuHaul Driver Assist</h1>
          <p>Report delays, breakdowns and ETAs — the operations team is alerted instantly.</p>
        </div>

        <form className="login-card__form" onSubmit={handleSubmit}>
          <label htmlFor="phone-input" className="login-card__label">
            Registered phone number
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
            {isLoading ? "Signing in…" : "Continue"}
          </button>
        </form>

        <div className="login-card__demo">
          <div className="login-card__demo-title">Demo drivers — tap to fill</div>
          {DEMO_DRIVERS.map((d) => (
            <div key={d.phone} className="login-card__demo-row">
              <span>
                {d.name} <em style={{ opacity: 0.7, fontStyle: "normal" }}>· {d.detail}</em>
              </span>
              <button type="button" onClick={() => setPhone(d.phone)} disabled={isLoading}>
                {d.phone}
              </button>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

export default LoginScreen;
