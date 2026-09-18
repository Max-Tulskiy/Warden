import type { ReactNode } from "react";
import { useNavigate } from "react-router-dom";

import { useAuth } from "../state/authContext";
import { LogoutIcon, ReportsIcon, SettingsIcon, ShieldIcon, StationsIcon } from "./icons";

function operatorInitials(username: string): string {
  return username.slice(0, 2).toUpperCase();
}

export function AppShell({ children, narrow }: { children: ReactNode; narrow?: boolean }) {
  const { username, setSession } = useAuth();
  const navigate = useNavigate();

  const handleLogout = () => {
    setSession(null);
    navigate("/login");
  };

  return (
    <div className="shell">
      <header className="shell-topbar">
        <div className="shell-brand">
          <ShieldIcon size={20} color="var(--accent)" />
          <span className="shell-brand-name">Warden</span>
        </div>
        <div className="shell-operator">
          {username && (
            <>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <span className="shell-avatar">{operatorInitials(username)}</span>
                <span className="text-secondary">{username}</span>
              </div>
              <div style={{ width: 1, height: 18, background: "var(--border-default)" }} />
            </>
          )}
          <button className="shell-logout" onClick={handleLogout}>
            <LogoutIcon />
            Выйти
          </button>
        </div>
      </header>

      <div className="shell-body">
        <nav className="shell-sidebar">
          <div className="shell-nav-item active">
            <StationsIcon />
            Станции
          </div>
          {/* Placeholders for future sections -- not yet real screens, so
              deliberately non-interactive rather than linking to nothing. */}
          <div className="shell-nav-item">
            <ReportsIcon />
            Отчёты
          </div>
          <div className="shell-nav-item">
            <SettingsIcon />
            Настройки
          </div>
        </nav>

        <main className={`shell-content${narrow ? " shell-content-narrow" : ""}`}>
          {children}
        </main>
      </div>
    </div>
  );
}
