import type { ReactNode } from "react";

import { useAuth } from "../state/authContext";
import { AppShell } from "./AppShell";

/**
 * Shows a screen only to an administrator. The server refuses the actions
 * anyway (D-10); this keeps an observer who opens the address by hand from
 * seeing a screen full of failures.
 *
 * While the role is not known it shows nothing, rather than a verdict that
 * would be wrong for an administrator whose role is still loading. An observer
 * gets a notice inside the panel and stays signed in.
 */
export function RequireAdmin({ children }: { children: ReactNode }) {
  const { role } = useAuth();
  if (!role) {
    return null;
  }
  if (role !== "admin") {
    return (
      <AppShell narrow>
        <section className="card">
          <p style={{ margin: 0 }}>Недостаточно прав для просмотра этого раздела</p>
        </section>
      </AppShell>
    );
  }
  return <>{children}</>;
}
