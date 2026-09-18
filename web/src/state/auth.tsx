import { useMemo, useState, type ReactNode } from "react";

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

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setTokenState] = useState<string | null>(() => readStored(TOKEN_KEY));
  const [username, setUsernameState] = useState<string | null>(() =>
    readStored(USERNAME_KEY),
  );

  const setSession = (session: { token: string; username: string } | null) => {
    setTokenState(session?.token ?? null);
    setUsernameState(session?.username ?? null);
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
  };

  const value = useMemo(() => ({ token, username, setSession }), [token, username]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
