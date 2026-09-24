import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Role } from "../../src/api/types";
import { AgentDetailPage } from "../../src/pages/AgentDetailPage";
import { AuthContext } from "../../src/state/authContext";

const policy = (windowHours: number) => ({
  max_request_window_hours: windowHours,
  enrollment_token_ttl_hours: 24,
  session_lifetime_minutes: 480,
  min_password_length: 12,
  max_report_events: 10_000,
  max_inventory_entries: 10_000,
  max_page_size: 2_000,
  overridden: false,
  defaults: {
    max_request_window_hours: 4,
    enrollment_token_ttl_hours: 24,
    session_lifetime_minutes: 480,
  },
  bounds: {
    max_request_window_hours: { min: 1, max: 4 },
    enrollment_token_ttl_hours: { min: 1, max: 168 },
    session_lifetime_minutes: { min: 5, max: 1440 },
  },
});

/** The station's data and, unless overridden, a policy whose window limit is 4 hours. */
function stubApi(onPolicy: () => Response = () => new Response(JSON.stringify(policy(4)))) {
  const requested: string[] = [];
  vi.spyOn(globalThis, "fetch").mockImplementation(
    vi.fn(async (input: RequestInfo | URL) => {
      const path = new URL(input.toString(), "http://x").pathname;
      requested.push(path);
      if (path === "/api/v1/policy") return onPolicy();
      if (path.endsWith("/events") || path.endsWith("/inventory/changes")) {
        return new Response(JSON.stringify([]), { status: 200 });
      }
      throw new Error(`unexpected request: ${path}`);
    }),
  );
  return requested;
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

describe("AgentDetailPage window limit", () => {
  it("shows an administrator the limit the server has in force", async () => {
    stubApi(() => new Response(JSON.stringify(policy(2))));

    renderDetail("admin");

    expect(
      await screen.findByText("Промежуток не должен превышать 2 часов"),
    ).toBeInTheDocument();
  });

  it("falls back to the four-hour ceiling when the policy cannot be loaded", async () => {
    stubApi(() => new Response(JSON.stringify({ detail: "boom" }), { status: 500 }));

    renderDetail("admin");

    await screen.findByRole("button", { name: "Запросить данные" });
    expect(screen.getByText("Промежуток не должен превышать 4 часов")).toBeInTheDocument();
  });

  it("does not fetch the policy for someone who cannot ask", async () => {
    const requested = stubApi();

    renderDetail("viewer");
    await screen.findByRole("heading", { name: "Отчёт за день" });

    expect(requested).not.toContain("/api/v1/policy");
  });
});
