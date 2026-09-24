import { useEffect, useMemo, useState, type ReactNode } from "react";

import { setUnauthorizedHandler } from "../api/client";
import { AuthContext } from "./authContext";

const TOKEN_KEY = "warden.token";
const USERNAME_KEY = "warden.username";

function readStored(key: string): string | null {
  try {
    return window.localStorage.getItem(key);
  } catch {
    // Private browsing or a blocked storage API -- fall back to a session
    // that simply is not remembered across a reload, not a crash.
    return null;
  }
}

type Session = { token: string; username: string };

function writeStored(session: Session | null): void {
  try {
    if (session) {
      window.localStorage.setItem(TOKEN_KEY, session.token);
      window.localStorage.setItem(USERNAME_KEY, session.username);
    } else {
      window.localStorage.removeItem(TOKEN_KEY);
      window.localStorage.removeItem(USERNAME_KEY);
    }
  } catch {
    // As above: storage is a convenience, not a requirement.
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setTokenState] = useState<string | null>(() => readStored(TOKEN_KEY));
  const [username, setUsernameState] = useState<string | null>(() =>
    readStored(USERNAME_KEY),
  );
  const [sessionEnded, setSessionEnded] = useState(false);

  const setSession = (session: Session | null) => {
    setTokenState(session?.token ?? null);
    setUsernameState(session?.username ?? null);
    writeStored(session);
    // Signing in again is what ends the notice; signing out on purpose is not
    // the server refusing anything, so it leaves the flag as it is.
    if (session) setSessionEnded(false);
  };

  // The API client calls this when the server refuses a request that carried
  // a token. Clearing the session is idempotent, so several refusals landing
  // together leave the same state, and `RequireAuth` sends the operator to
  // sign-in on the missing token.
  useEffect(() => {
    setUnauthorizedHandler(() => {
      setTokenState(null);
      setUsernameState(null);
      writeStored(null);
      setSessionEnded(true);
    });
    return () => setUnauthorizedHandler(null);
  }, []);

  const value = useMemo(
    () => ({ token, username, sessionEnded, setSession }),
    [token, username, sessionEnded],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
