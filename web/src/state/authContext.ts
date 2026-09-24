import { createContext, useContext } from "react";

import type { Role } from "../api/types";

export interface AuthContextValue {
  token: string | null;
  username: string | null;
  /**
   * True from the moment the server refuses the session until the operator
   * signs in again. A voluntary sign-out does not set it. Optional so a
   * context built by hand, as the tests do, means "not ended".
   */
  sessionEnded?: boolean;
  /**
   * What the signed-in person may do, from the server. Null while it is being
   * loaded, when nobody is signed in, and if it could not be loaded; the panel
   * offers nothing that needs a role until it is known. Optional, like
   * `sessionEnded`, so a context built by hand means "unknown".
   */
  role?: Role | null;
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
