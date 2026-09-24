import { useEffect, useMemo, useState, type ReactNode } from "react";

import { getMe, setForbiddenHandler, setUnauthorizedHandler } from "../api/client";
import type { Role } from "../api/types";
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

  // The role is kept with the token it was loaded for, so signing in as someone
  // else never shows the previous person's role while the new one is loading.
  const [loadedRole, setLoadedRole] = useState<{ token: string; role: Role } | null>(null);
  const [roleReloads, setRoleReloads] = useState(0);
  const role = loadedRole && loadedRole.token === token ? loadedRole.role : null;

  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    getMe(token)
      .then((me) => {
        if (!cancelled) setLoadedRole({ token, role: me.role });
      })
      .catch(() => {
        // The session itself is judged by the 401 hook; a role that cannot be
        // loaded just stays unknown, and nothing role-gated is offered.
      });
    return () => {
      cancelled = true;
    };
  }, [token, roleReloads]);

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
    // A 403 means the person's role may have changed since the panel loaded it:
    // reload it, and the navigation and controls follow.
    setForbiddenHandler(() => setRoleReloads((count) => count + 1));
    return () => {
      setUnauthorizedHandler(null);
      setForbiddenHandler(null);
    };
  }, []);

  const value = useMemo(
    () => ({ token, username, sessionEnded, role, setSession }),
    [token, username, sessionEnded, role],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
