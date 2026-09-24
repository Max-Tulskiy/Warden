import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Role } from "../../src/api/types";
import { AgentDetailPage } from "../../src/pages/AgentDetailPage";
import { AuthContext } from "../../src/state/authContext";

function stubApi() {
  return vi.spyOn(globalThis, "fetch").mockImplementation(
    vi.fn(async (input: RequestInfo | URL) => {
      const path = new URL(input.toString(), "http://x").pathname;
      if (path.endsWith("/events") || path.endsWith("/inventory/changes")) {
        return new Response(JSON.stringify([]), { status: 200 });
      }
      throw new Error(`unexpected request: ${path}`);
    }),
  );
}

function renderDetail(role: Role | null) {
  return render(
    <MemoryRouter initialEntries={["/agents/a-1"]}>
      <AuthContext.Provider
        value={{ token: "operator-token", username: "someone", role, setSession: vi.fn() }}
      >
        <Routes>
          <Route path="/agents/:agentId" element={<AgentDetailPage />} />
        </Routes>
      </AuthContext.Provider>
    </MemoryRouter>,
  );
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("AgentDetailPage window request by role", () => {
  it("lets an administrator ask a station for data", async () => {
    stubApi();

    renderDetail("admin");

    expect(
      await screen.findByRole("heading", { name: "Запросить данные за промежуток" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Запросить данные" })).toBeInTheDocument();
  });

  it.each<[string, Role | null]>([
    ["an observer", "viewer"],
    ["a person whose role is not known yet", null],
  ])("does not let %s ask, and still shows the station's data", async (_who, role) => {
    stubApi();

    renderDetail(role);

    expect(
      await screen.findByRole("heading", { name: "Отчёт за день" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("heading", { name: "Запросить данные за промежуток" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Запросить данные" }),
    ).not.toBeInTheDocument();
  });
});
