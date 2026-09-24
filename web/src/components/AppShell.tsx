import type { ReactNode } from "react";
import { NavLink, useNavigate } from "react-router-dom";

import { useAuth } from "../state/authContext";
import {
  AuditIcon,
  LogoutIcon,
  ReportsIcon,
  SettingsIcon,
  ShieldIcon,
  StationsIcon,
} from "./icons";

function operatorInitials(username: string): string {
  return username.slice(0, 2).toUpperCase();
}

function navClassName({ isActive }: { isActive: boolean }): string {
  return isActive ? "shell-nav-item active" : "shell-nav-item";
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
          <NavLink to="/agents" className={navClassName}>
            <StationsIcon />
            Станции
          </NavLink>
          <NavLink to="/reports" className={navClassName}>
            <ReportsIcon />
            Отчёты
          </NavLink>
          <NavLink to="/audit" className={navClassName}>
            <AuditIcon />
            Журнал
          </NavLink>
          <NavLink to="/settings" className={navClassName}>
            <SettingsIcon />
            Настройки
          </NavLink>
        </nav>

        <main className={`shell-content${narrow ? " shell-content-narrow" : ""}`}>
          {children}
        </main>
      </div>
    </div>
  );
}
