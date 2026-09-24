import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import type { Role } from "../../src/api/types";
import { RequireAdmin } from "../../src/components/RequireAdmin";
import { AuthContext } from "../../src/state/authContext";

const NO_RIGHTS = "Недостаточно прав для просмотра этого раздела";

function renderGuarded(role: Role | null | undefined) {
  const setSession = vi.fn();
  render(
    <MemoryRouter>
      <AuthContext.Provider
        value={{ token: "operator-token", username: "someone", role, setSession }}
      >
        <RequireAdmin>
          <p>the administrator screen</p>
        </RequireAdmin>
      </AuthContext.Provider>
    </MemoryRouter>,
  );
  return setSession;
}

describe("RequireAdmin", () => {
  it("shows its content to an administrator", () => {
    renderGuarded("admin");

    expect(screen.getByText("the administrator screen")).toBeInTheDocument();
    expect(screen.queryByText(NO_RIGHTS)).not.toBeInTheDocument();
  });

  it("tells an observer they lack the rights, inside the shell, without their content", () => {
    renderGuarded("viewer");

    expect(screen.getByText(NO_RIGHTS)).toBeInTheDocument();
    expect(screen.queryByText("the administrator screen")).not.toBeInTheDocument();
    // Still the panel, not a dead end: the navigation is there.
    expect(screen.getByRole("link", { name: "Станции" })).toBeInTheDocument();
  });

  it("does not sign an observer out", () => {
    const setSession = renderGuarded("viewer");

    expect(setSession).not.toHaveBeenCalled();
  });

  it.each([null, undefined])(
    "shows neither content nor a verdict while the role is %s",
    (role) => {
      renderGuarded(role);

      expect(screen.queryByText("the administrator screen")).not.toBeInTheDocument();
      expect(screen.queryByText(NO_RIGHTS)).not.toBeInTheDocument();
    },
  );
});
