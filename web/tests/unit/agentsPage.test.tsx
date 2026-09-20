import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AgentsPage } from "../../src/pages/AgentsPage";
import { AuthContext } from "../../src/state/authContext";

function renderAgentsPage() {
  return render(
    <MemoryRouter>
      <AuthContext.Provider
        value={{
          token: "operator-token",
          username: "admin",
          setSession: vi.fn(),
        }}
      >
        <AgentsPage />
      </AuthContext.Provider>
    </MemoryRouter>,
  );
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("AgentsPage", () => {
  it("issues an enrollment token from the station list", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const path = input.toString();
        if (path === "/api/v1/agents") {
          return new Response(JSON.stringify([]), { status: 200 });
        }
        if (path === "/api/v1/enrollment-tokens") {
          expect(init?.method).toBe("POST");
          expect(init?.headers).toMatchObject({
            Authorization: "Bearer operator-token",
          });
          return new Response(
            JSON.stringify({
              token: "enroll-token-123",
              expires_at: "2026-09-16T12:00:00Z",
            }),
            { status: 201 },
          );
        }
        throw new Error(`unexpected request: ${path}`);
      }),
    );

    renderAgentsPage();

    await userEvent.click(screen.getByRole("button", { name: /Выпустить токен/ }));

    expect(await screen.findByText("enroll-token-123")).toBeInTheDocument();
    expect(screen.getByText(/Действует до/)).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/enrollment-tokens",
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("shows a disabled station as disabled and leaves it out of the online count", async () => {
    const seenJustNow = new Date().toISOString();
    const station = (id: string, hostname: string, status: "active" | "disabled") => ({
      id,
      hostname,
      os: "linux",
      status,
      enrolled_at: seenJustNow,
      last_seen_at: seenJustNow,
    });
    vi.spyOn(globalThis, "fetch").mockImplementation(
      vi.fn(async (input: RequestInfo | URL) => {
        if (input.toString() === "/api/v1/agents") {
          return new Response(
            JSON.stringify([
              station("a-1", "WS-01", "active"),
              station("a-2", "WS-02", "disabled"),
            ]),
            { status: 200 },
          );
        }
        throw new Error(`unexpected request: ${input.toString()}`);
      }),
    );

    renderAgentsPage();

    expect(await screen.findByText("отключена")).toBeInTheDocument();
    expect(screen.getByText("в сети")).toBeInTheDocument();
    expect(screen.getByText("2 всего · 1 в сети")).toBeInTheDocument();
  });
});
