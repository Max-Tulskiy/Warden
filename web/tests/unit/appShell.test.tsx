import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { AppShell } from "../../src/components/AppShell";
import { AuthContext } from "../../src/state/authContext";

function renderShellAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AuthContext.Provider
        value={{ token: "operator-token", username: "admin", setSession: vi.fn() }}
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
    expect(screen.getByRole("link", { name: "Настройки" })).toHaveAttribute(
      "href",
      "/settings",
    );
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
});
