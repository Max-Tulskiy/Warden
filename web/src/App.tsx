import { Navigate, Route, Routes } from "react-router-dom";

import { AgentDetailPage } from "./pages/AgentDetailPage";
import { AgentsPage } from "./pages/AgentsPage";
import { AuditPage } from "./pages/AuditPage";
import { RequireAdmin } from "./components/RequireAdmin";
import { LoginPage } from "./pages/LoginPage";
import { OperatorsPage } from "./pages/OperatorsPage";
import { ReportsPage } from "./pages/ReportsPage";
import { SettingsPage } from "./pages/SettingsPage";
import { useAuth } from "./state/authContext";

function RequireAuth({ children }: { children: React.ReactNode }) {
  const { token } = useAuth();
  if (!token) {
    return <Navigate to="/login" replace />;
  }
  return <>{children}</>;
}

export function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route
        path="/agents"
        element={
          <RequireAuth>
            <AgentsPage />
          </RequireAuth>
        }
      />
      <Route
        path="/agents/:agentId"
        element={
          <RequireAuth>
            <AgentDetailPage />
          </RequireAuth>
        }
      />
      <Route
        path="/reports"
        element={
          <RequireAuth>
            <ReportsPage />
          </RequireAuth>
        }
      />
      <Route
        path="/audit"
        element={
          <RequireAuth>
            <RequireAdmin>
              <AuditPage />
            </RequireAdmin>
          </RequireAuth>
        }
      />
      <Route
        path="/operators"
        element={
          <RequireAuth>
            <RequireAdmin>
              <OperatorsPage />
            </RequireAdmin>
          </RequireAuth>
        }
      />
      <Route
        path="/settings"
        element={
          <RequireAuth>
            <SettingsPage />
          </RequireAuth>
        }
      />
      <Route path="*" element={<Navigate to="/agents" replace />} />
    </Routes>
  );
}
