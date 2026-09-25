import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Role } from "../../src/api/types";
import { AgentsPage } from "../../src/pages/AgentsPage";
import { AuthContext } from "../../src/state/authContext";

function renderAgentsPage(role: Role | null = "admin") {
  return render(
    <MemoryRouter>
      <AuthContext.Provider
        value={{
          token: "operator-token",
          username: "admin",
          role,
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

  describe("enrollment tokens by role", () => {
    const stubStations = () =>
      vi.spyOn(globalThis, "fetch").mockImplementation(
        vi.fn(async (input: RequestInfo | URL) => {
          const path = input.toString();
          if (path === "/api/v1/agents") {
            return new Response(JSON.stringify([]), { status: 200 });
          }
          throw new Error(`unexpected request: ${path}`);
        }),
      );

    it("offers the button to an administrator", async () => {
      stubStations();

      renderAgentsPage("admin");

      expect(
        await screen.findByRole("button", { name: /Выпустить токен/ }),
      ).toBeInTheDocument();
    });

    it.each<[string, Role | null]>([
      ["an observer", "viewer"],
      ["a person whose role is not known yet", null],
    ])(
      "does not offer the button to %s, and still lists the stations",
      async (_who, role) => {
        const fetchMock = stubStations();

        renderAgentsPage(role);

        await screen.findByRole("heading", { name: "Станции" });
        expect(
          screen.queryByRole("button", { name: /Выпустить токен/ }),
        ).not.toBeInTheDocument();
        expect(fetchMock).toHaveBeenCalledWith("/api/v1/agents", expect.anything());
      },
    );
  });

  describe("the server's certificate fingerprint", () => {
    const FINGERPRINT = "b171395da10849824071f08074ebc29945c7dd3e3187480647ea0a60cc130833";

    function stubServer(authority: () => Response | Promise<Response>) {
      return vi.spyOn(globalThis, "fetch").mockImplementation(
        vi.fn(async (input: RequestInfo | URL) => {
          const path = input.toString();
          if (path === "/api/v1/agents") {
            return new Response(JSON.stringify([]), { status: 200 });
          }
          if (path === "/api/v1/tls/ca") {
            return authority();
          }
          throw new Error(`unexpected request: ${path}`);
        }),
      );
    }

    it("shows an administrator the fingerprint to compare with the agent's window", async () => {
      stubServer(
        () =>
          new Response(
            JSON.stringify({ pem: "-----BEGIN CERTIFICATE-----", sha256: FINGERPRINT }),
            {
              status: 200,
            },
          ),
      );

      renderAgentsPage("admin");

      expect(
        await screen.findByText("Отпечаток сертификата сервера (SHA-256)"),
      ).toBeInTheDocument();
      expect(
        screen.getByText(
          "B1:71:39:5D:A1:08:49:82:40:71:F0:80:74:EB:C2:99:45:C7:DD:3E:31:87:48:06:47:EA:0A:60:CC:13:08:33",
        ),
      ).toBeInTheDocument();
      expect(
        screen.getByText(/Сверьте его с отпечатком в окне настройки агента/),
      ).toBeInTheDocument();
    });

    it("asks for it without a session, since a station that has not enrolled has none", async () => {
      const fetchMock = stubServer(
        () =>
          new Response(JSON.stringify({ pem: "x", sha256: FINGERPRINT }), { status: 200 }),
      );

      renderAgentsPage("admin");
      await screen.findByText("Отпечаток сертификата сервера (SHA-256)");

      const call = fetchMock.mock.calls.find(([path]) => path === "/api/v1/tls/ca");
      expect(call?.[1]?.headers).not.toHaveProperty("Authorization");
    });

    it("says there is nothing to compare when the server has no authority of its own", async () => {
      stubServer(() => new Response(JSON.stringify({ detail: "none" }), { status: 404 }));

      renderAgentsPage("admin");

      expect(
        await screen.findByText(/сертификат, который система уже проверяет/),
      ).toBeInTheDocument();
      expect(
        screen.queryByText("Отпечаток сертификата сервера (SHA-256)"),
      ).not.toBeInTheDocument();
    });

    it("shows nothing, and the page still works, when the request fails", async () => {
      stubServer(() => {
        throw new Error("network down");
      });

      renderAgentsPage("admin");

      expect(
        await screen.findByText("Нет зарегистрированных агентов."),
      ).toBeInTheDocument();
      expect(
        screen.queryByText("Отпечаток сертификата сервера (SHA-256)"),
      ).not.toBeInTheDocument();
      expect(
        screen.queryByText(/сертификат, который система уже проверяет/),
      ).not.toBeInTheDocument();
    });

    it("does not show an observer the block or ask for it", async () => {
      const fetchMock = stubServer(
        () =>
          new Response(JSON.stringify({ pem: "x", sha256: FINGERPRINT }), { status: 200 }),
      );

      renderAgentsPage("viewer");
      await screen.findByText("Нет зарегистрированных агентов.");

      expect(
        screen.queryByText("Отпечаток сертификата сервера (SHA-256)"),
      ).not.toBeInTheDocument();
      expect(fetchMock.mock.calls.some(([path]) => path === "/api/v1/tls/ca")).toBe(false);
    });
  });
});
