import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Role } from "../../src/api/types";
import { SettingsPage } from "../../src/pages/SettingsPage";
import { AuthContext } from "../../src/state/authContext";

const policy = {
  max_request_window_hours: 4,
  enrollment_token_ttl_hours: 24,
  session_lifetime_minutes: 480,
  min_password_length: 12,
  max_report_events: 10_000,
  max_inventory_entries: 10_000,
  max_page_size: 2_000,
};

const lastSeen = new Date().toISOString();
const stations = [
  { id: "a-1", hostname: "WS-01", os: "linux", status: "active" },
  { id: "a-2", hostname: "WS-02", os: "windows", status: "disabled" },
].map((station) => ({
  ...station,
  enrolled_at: "2026-08-01T00:00:00Z",
  last_seen_at: lastSeen,
}));

const NEW_PASSWORD = "a-brand-new-passphrase";

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status });
}

interface Overrides {
  password?: () => Response;
  patch?: () => Response;
  logoutAll?: () => Response;
}

/** Stubs every endpoint the page uses and records the writes it makes. */
function stubApi(overrides: Overrides = {}) {
  const calls = {
    password: [] as { current_password: string; new_password: string }[],
    patch: [] as { id: string; status: string }[],
    logoutAll: 0,
  };
  vi.spyOn(globalThis, "fetch").mockImplementation(
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = new URL(input.toString(), "http://x").pathname;
      const method = init?.method ?? "GET";
      if (path === "/api/v1/policy") return json(policy);
      if (path === "/api/v1/agents" && method === "GET") return json(stations);
      if (path === "/api/v1/auth/password" && method === "POST") {
        calls.password.push(JSON.parse(init?.body as string));
        return (
          overrides.password?.() ??
          json({ access_token: "new-token", token_type: "bearer" })
        );
      }
      if (path === "/api/v1/auth/logout-all" && method === "POST") {
        calls.logoutAll += 1;
        return overrides.logoutAll?.() ?? new Response(null, { status: 204 });
      }
      const station = path.match(/^\/api\/v1\/agents\/([^/]+)$/);
      if (station && method === "PATCH") {
        const { status } = JSON.parse(init?.body as string);
        calls.patch.push({ id: station[1], status });
        return (
          overrides.patch?.() ??
          json({ ...stations.find((item) => item.id === station[1]), status })
        );
      }
      throw new Error(`unexpected request: ${method} ${path}`);
    }),
  );
  return calls;
}

function renderSettingsPage(role: Role | null = "admin") {
  const setSession = vi.fn();
  render(
    <MemoryRouter>
      <AuthContext.Provider
        value={{ token: "operator-token", username: "admin", role, setSession }}
      >
        <SettingsPage />
      </AuthContext.Provider>
    </MemoryRouter>,
  );
  return setSession;
}

async function fillPasswordForm(current: string, next: string, repeat: string) {
  await screen.findByText("12 симв.");
  await userEvent.type(screen.getByLabelText("Текущий пароль"), current);
  await userEvent.type(screen.getByLabelText("Новый пароль"), next);
  await userEvent.type(screen.getByLabelText("Повторите новый пароль"), repeat);
  await userEvent.click(screen.getByRole("button", { name: "Сменить пароль" }));
}

function stationRow(hostname: string) {
  return screen.getByRole("row", { name: new RegExp(hostname) });
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("SettingsPage policy", () => {
  it("shows the server's limits, with units, and nothing editable", async () => {
    stubApi();

    renderSettingsPage();

    const card = (await screen.findByRole("heading", { name: "Политика сервера" })).closest(
      "section",
    )!;
    const valueOf = (label: string) =>
      within(screen.getByText(label).closest("div")!).getByText(/\S/, {
        selector: "dd",
      });
    expect(valueOf("Максимальное окно запроса к агенту")).toHaveTextContent("4 ч");
    expect(valueOf("Срок действия токена регистрации")).toHaveTextContent("24 ч");
    expect(valueOf("Срок действия сессии")).toHaveTextContent("8 ч");
    expect(valueOf("Минимальная длина пароля")).toHaveTextContent("12 симв.");
    expect(valueOf("Максимум событий в одном отчёте агента")).toHaveTextContent(/10\s000/);
    expect(valueOf("Максимум записей на страницу отчёта")).toHaveTextContent(/2\s000/);
    expect(within(card).queryAllByRole("textbox")).toHaveLength(0);
    expect(within(card).queryAllByRole("spinbutton")).toHaveLength(0);
  });
});

describe("SettingsPage password change", () => {
  it("does not send a mismatched repeat", async () => {
    const calls = stubApi();
    renderSettingsPage();

    await fillPasswordForm("current-secret-1", NEW_PASSWORD, `${NEW_PASSWORD}x`);

    expect(await screen.findByText("Пароли не совпадают")).toBeInTheDocument();
    expect(calls.password).toHaveLength(0);
  });

  it("does not send a password shorter than the policy minimum", async () => {
    const calls = stubApi();
    renderSettingsPage();

    await fillPasswordForm("current-secret-1", "short", "short");

    expect(
      await screen.findByText("Новый пароль должен быть не короче 12 символов"),
    ).toBeInTheDocument();
    expect(calls.password).toHaveLength(0);
  });

  it("does not send a new password equal to the current one", async () => {
    const calls = stubApi();
    renderSettingsPage();

    await fillPasswordForm(NEW_PASSWORD, NEW_PASSWORD, NEW_PASSWORD);

    expect(
      await screen.findByText("Новый пароль должен отличаться от текущего"),
    ).toBeInTheDocument();
    expect(calls.password).toHaveLength(0);
  });

  it("explains a wrong current password", async () => {
    stubApi({ password: () => json({ detail: "Current password is incorrect" }, 400) });
    renderSettingsPage();

    await fillPasswordForm("wrong-current-1", NEW_PASSWORD, NEW_PASSWORD);

    expect(await screen.findByText("Неверный текущий пароль")).toBeInTheDocument();
  });

  it("explains a throttled attempt", async () => {
    stubApi({ password: () => json({ detail: "Too many failed attempts" }, 429) });
    renderSettingsPage();

    await fillPasswordForm("current-secret-1", NEW_PASSWORD, NEW_PASSWORD);

    expect(
      await screen.findByText("Слишком много попыток. Повторите позже"),
    ).toBeInTheDocument();
  });

  it("confirms the change, says the other sessions ended, and clears the form", async () => {
    const calls = stubApi();
    renderSettingsPage();

    await fillPasswordForm("current-secret-1", NEW_PASSWORD, NEW_PASSWORD);

    expect(
      await screen.findByText("Пароль изменён. Остальные сеансы завершены."),
    ).toBeInTheDocument();
    expect(screen.queryByText(/остаются действительными/)).not.toBeInTheDocument();
    expect(calls.password).toEqual([
      { current_password: "current-secret-1", new_password: NEW_PASSWORD },
    ]);
    expect(screen.getByLabelText("Текущий пароль")).toHaveValue("");
    expect(screen.getByLabelText("Новый пароль")).toHaveValue("");
  });

  it("keeps this session by storing the token the server returned", async () => {
    stubApi();
    const setSession = renderSettingsPage();

    await fillPasswordForm("current-secret-1", NEW_PASSWORD, NEW_PASSWORD);

    await screen.findByText("Пароль изменён. Остальные сеансы завершены.");
    expect(setSession).toHaveBeenCalledTimes(1);
    expect(setSession).toHaveBeenCalledWith({ token: "new-token", username: "admin" });
  });

  it("leaves the session alone when the change fails", async () => {
    stubApi({ password: () => json({ detail: "Current password is incorrect" }, 400) });
    const setSession = renderSettingsPage();

    await fillPasswordForm("wrong-current-1", NEW_PASSWORD, NEW_PASSWORD);

    await screen.findByText("Неверный текущий пароль");
    expect(setSession).not.toHaveBeenCalled();
  });

  it("no longer says a password change leaves other sessions valid", async () => {
    stubApi();
    renderSettingsPage();

    await screen.findByText("12 симв.");

    expect(screen.queryByText(/не завершает уже выданные сессии/)).not.toBeInTheDocument();
    expect(
      screen.getByText(/Смена пароля завершает все остальные сеансы/),
    ).toBeInTheDocument();
  });
});

describe("SettingsPage sessions", () => {
  const sessionsCard = () =>
    screen.getByRole("heading", { name: "Сеансы" }).closest("section")!;

  it("says that ending all sessions signs the operator out here too", async () => {
    stubApi();
    renderSettingsPage();

    await screen.findByText("12 симв.");

    expect(within(sessionsCard()).getByText(/включая это/)).toBeInTheDocument();
  });

  it("asks before doing anything, and sends nothing until confirmed", async () => {
    const calls = stubApi();
    const setSession = renderSettingsPage();
    await screen.findByText("12 симв.");

    await userEvent.click(
      within(sessionsCard()).getByRole("button", { name: "Завершить все сеансы" }),
    );

    expect(
      within(sessionsCard()).getByText("Завершить все сеансы, включая этот?"),
    ).toBeInTheDocument();
    expect(calls.logoutAll).toBe(0);
    expect(setSession).not.toHaveBeenCalled();
  });

  it("sends nothing when the operator cancels", async () => {
    const calls = stubApi();
    const setSession = renderSettingsPage();
    await screen.findByText("12 симв.");
    await userEvent.click(
      within(sessionsCard()).getByRole("button", { name: "Завершить все сеансы" }),
    );

    await userEvent.click(within(sessionsCard()).getByRole("button", { name: "Отмена" }));

    expect(calls.logoutAll).toBe(0);
    expect(setSession).not.toHaveBeenCalled();
    expect(
      within(sessionsCard()).getByRole("button", { name: "Завершить все сеансы" }),
    ).toBeInTheDocument();
  });

  it("ends the sessions and clears this one when confirmed", async () => {
    const calls = stubApi();
    const setSession = renderSettingsPage();
    await screen.findByText("12 симв.");
    await userEvent.click(
      within(sessionsCard()).getByRole("button", { name: "Завершить все сеансы" }),
    );

    await userEvent.click(
      within(sessionsCard()).getByRole("button", { name: "Да, завершить" }),
    );

    await waitFor(() => expect(setSession).toHaveBeenCalledWith(null));
    expect(calls.logoutAll).toBe(1);
  });

  it("keeps the session and says so when the server fails", async () => {
    stubApi({ logoutAll: () => json({ detail: "boom" }, 500) });
    const setSession = renderSettingsPage();
    await screen.findByText("12 симв.");
    await userEvent.click(
      within(sessionsCard()).getByRole("button", { name: "Завершить все сеансы" }),
    );

    await userEvent.click(
      within(sessionsCard()).getByRole("button", { name: "Да, завершить" }),
    );

    expect(await screen.findByText("Не удалось завершить сеансы")).toBeInTheDocument();
    expect(setSession).not.toHaveBeenCalled();
  });
});

describe("SettingsPage stations", () => {
  it("asks for confirmation before disabling, then updates the row", async () => {
    const calls = stubApi();
    renderSettingsPage();
    await screen.findByRole("row", { name: /WS-01/ });

    await userEvent.click(
      within(stationRow("WS-01")).getByRole("button", { name: "Отключить" }),
    );
    expect(calls.patch).toHaveLength(0);
    expect(screen.getByText(/Отключить станцию WS-01\?/)).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Да, отключить" }));

    expect(calls.patch).toEqual([{ id: "a-1", status: "disabled" }]);
    const row = await screen.findByRole("row", { name: /WS-01.*отключена/ });
    expect(within(row).getByRole("button", { name: "Включить" })).toBeInTheDocument();
  });

  it("does nothing when the confirmation is cancelled", async () => {
    const calls = stubApi();
    renderSettingsPage();
    await screen.findByRole("row", { name: /WS-01/ });

    await userEvent.click(
      within(stationRow("WS-01")).getByRole("button", { name: "Отключить" }),
    );
    await userEvent.click(screen.getByRole("button", { name: "Отмена" }));

    expect(calls.patch).toHaveLength(0);
    expect(
      within(stationRow("WS-01")).getByRole("button", { name: "Отключить" }),
    ).toBeInTheDocument();
  });

  it("re-enables a station without asking", async () => {
    const calls = stubApi();
    renderSettingsPage();
    await screen.findByRole("row", { name: /WS-02/ });

    await userEvent.click(
      within(stationRow("WS-02")).getByRole("button", { name: "Включить" }),
    );

    expect(calls.patch).toEqual([{ id: "a-2", status: "active" }]);
    expect(
      await within(await screen.findByRole("row", { name: /WS-02/ })).findByRole("button", {
        name: "Отключить",
      }),
    ).toBeInTheDocument();
  });

  it("reports a failed status change", async () => {
    stubApi({ patch: () => json({ detail: "boom" }, 500) });
    renderSettingsPage();
    await screen.findByRole("row", { name: /WS-02/ });

    await userEvent.click(
      within(stationRow("WS-02")).getByRole("button", { name: "Включить" }),
    );

    expect(
      await screen.findByText("Не удалось изменить статус станции"),
    ).toBeInTheDocument();
  });
});

describe("SettingsPage by role", () => {
  const requestedPaths = (fetchMock: ReturnType<typeof vi.spyOn>) =>
    fetchMock.mock.calls.map(([input]) => new URL(String(input), "http://x").pathname);

  it("gives an administrator the stations card", async () => {
    stubApi();
    renderSettingsPage("admin");

    expect(await screen.findByRole("heading", { name: "Станции" })).toBeInTheDocument();
    expect(await screen.findByText("WS-01")).toBeInTheDocument();
  });

  it.each<[string, Role | null]>([
    ["an observer", "viewer"],
    ["a person whose role is not known yet", null],
  ])("keeps the stations card from %s but leaves the other cards", async (_who, role) => {
    stubApi();
    renderSettingsPage(role);

    await screen.findByText("12 симв.");

    expect(screen.queryByRole("heading", { name: "Станции" })).not.toBeInTheDocument();
    expect(screen.queryByText("WS-01")).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Смена пароля" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Сеансы" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Политика сервера" })).toBeInTheDocument();
  });

  it("does not fetch the station list for someone who cannot use it", async () => {
    stubApi();
    renderSettingsPage("viewer");
    await screen.findByText("12 симв.");

    const paths = requestedPaths(vi.mocked(globalThis.fetch) as never);

    expect(paths).not.toContain("/api/v1/agents");
    expect(paths).toContain("/api/v1/policy");
  });
});
