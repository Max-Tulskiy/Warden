import { createContext, useContext } from "react";

export interface AuthContextValue {
  token: string | null;
  username: string | null;
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
