import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import type { Role } from "../../src/api/types";
import { AppShell } from "../../src/components/AppShell";
import { AuthContext } from "../../src/state/authContext";

/** An administrator unless a role is passed, `undefined` included: a default
 * parameter would swallow an explicit `undefined`, which is a case under test. */
function renderShellAt(path: string, ...given: [] | [Role | null | undefined]) {
  const role = given.length > 0 ? given[0] : "admin";
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AuthContext.Provider
        value={{ token: "operator-token", username: "admin", role, setSession: vi.fn() }}
      >
        <AppShell>
          <p>content</p>
        </AppShell>
      </AuthContext.Provider>
    </MemoryRouter>,
  );
}

function isActive(name: string): boolean {
  return screen.getByRole("link", { name }).classList.contains("active");
}

describe("AppShell navigation", () => {
  it("links each sidebar section to its own route", () => {
    renderShellAt("/agents");

    expect(screen.getByRole("link", { name: "Станции" })).toHaveAttribute(
      "href",
      "/agents",
    );
    expect(screen.getByRole("link", { name: "Отчёты" })).toHaveAttribute(
      "href",
      "/reports",
    );
    expect(screen.getByRole("link", { name: "Журнал" })).toHaveAttribute("href", "/audit");
    expect(screen.getByRole("link", { name: "Операторы" })).toHaveAttribute(
      "href",
      "/operators",
    );
    expect(screen.getByRole("link", { name: "Настройки" })).toHaveAttribute(
      "href",
      "/settings",
    );
  });

  it("lists an administrator's sections in order, with the log and accounts before the settings", () => {
    renderShellAt("/agents");

    const names = screen.getAllByRole("link").map((link) => link.textContent);
    expect(names).toEqual(["Станции", "Отчёты", "Журнал", "Операторы", "Настройки"]);
  });

  it("keeps Stations active on a station's detail page", () => {
    renderShellAt("/agents/6f0d0f0e-0000-4000-8000-000000000001");

    expect(isActive("Станции")).toBe(true);
    expect(isActive("Отчёты")).toBe(false);
    expect(isActive("Настройки")).toBe(false);
  });

  it("marks Reports active on /reports only", () => {
    renderShellAt("/reports");

    expect(isActive("Отчёты")).toBe(true);
    expect(isActive("Станции")).toBe(false);
    expect(isActive("Настройки")).toBe(false);
  });

  it("marks Settings active on /settings only", () => {
    renderShellAt("/settings");

    expect(isActive("Настройки")).toBe(true);
    expect(isActive("Станции")).toBe(false);
    expect(isActive("Отчёты")).toBe(false);
  });

  it("marks Журнал active on /audit only", () => {
    renderShellAt("/audit");

    expect(isActive("Журнал")).toBe(true);
    expect(isActive("Станции")).toBe(false);
    expect(isActive("Отчёты")).toBe(false);
    expect(isActive("Настройки")).toBe(false);
  });

  it("leaves Журнал inactive on the other screens", () => {
    renderShellAt("/reports");

    expect(isActive("Журнал")).toBe(false);
  });

  it("marks Операторы active on /operators only", () => {
    renderShellAt("/operators");

    expect(isActive("Операторы")).toBe(true);
    expect(isActive("Журнал")).toBe(false);
    expect(isActive("Настройки")).toBe(false);
  });
});

describe("AppShell by role", () => {
  it("offers an observer only what they can use", () => {
    renderShellAt("/agents", "viewer");

    const names = screen.getAllByRole("link").map((link) => link.textContent);
    expect(names).toEqual(["Станции", "Отчёты", "Настройки"]);
  });

  it("offers nothing role-gated while the role is not known", () => {
    renderShellAt("/agents", null);

    const names = screen.getAllByRole("link").map((link) => link.textContent);
    expect(names).toEqual(["Станции", "Отчёты", "Настройки"]);
  });

  it("offers nothing role-gated when the context carries no role at all", () => {
    renderShellAt("/agents", undefined);

    expect(screen.queryByRole("link", { name: "Журнал" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Операторы" })).not.toBeInTheDocument();
  });

  it("says which role the signed-in person has, in Russian", () => {
    const { unmount } = renderShellAt("/agents", "admin");
    expect(screen.getByText("администратор")).toBeInTheDocument();
    unmount();

    renderShellAt("/agents", "viewer");
    expect(screen.getByText("наблюдатель")).toBeInTheDocument();
  });

  it("shows no role label until the role is known", () => {
    renderShellAt("/agents", null);

    expect(screen.queryByText("администратор")).not.toBeInTheDocument();
    expect(screen.queryByText("наблюдатель")).not.toBeInTheDocument();
  });
});
