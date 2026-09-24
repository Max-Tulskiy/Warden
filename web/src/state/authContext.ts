import { createContext, useContext } from "react";

export interface AuthContextValue {
  token: string | null;
  username: string | null;
  /**
   * True from the moment the server refuses the session until the operator
   * signs in again. A voluntary sign-out does not set it. Optional so a
   * context built by hand, as the tests do, means "not ended".
   */
  sessionEnded?: boolean;
  setSession: (session: { token: string; username: string } | null) => void;
}

export const AuthContext = createContext<AuthContextValue | null>(null);

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (context === null) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}
