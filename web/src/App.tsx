import { Navigate, Route, Routes } from "react-router-dom";

import { AgentDetailPage } from "./pages/AgentDetailPage";
import { AgentsPage } from "./pages/AgentsPage";
import { LoginPage } from "./pages/LoginPage";
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
      <Route path="*" element={<Navigate to="/agents" replace />} />
    </Routes>
  );
}
