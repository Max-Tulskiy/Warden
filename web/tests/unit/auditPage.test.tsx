import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AuditPage } from "../../src/pages/AuditPage";
import { AuthContext } from "../../src/state/authContext";

const HOUR = 3_600_000;
const PAGE_SIZE = 500;
const STATION_ID = "6f1c2a94-1111-4222-8333-444455556666";

const stations = [
  {
    id: STATION_ID,
    hostname: "WS-01",
    os: "linux",
    status: "active",
    enrolled_at: "2026-08-01T00:00:00Z",
    last_seen_at: "2026-09-01T12:00:00Z",
  },
];

function entry(n: number, overrides: Record<string, unknown> = {}) {
  return {
    id: `id-${n}`,
    actor: "admin",
    action: "operator.login",
    target: "admin",
    occurred_at: "2026-09-01T12:00:00Z",
    detail: {},
    ...overrides,
  };
}

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status });
}

/** Stubs the two endpoints the page uses and records every log request. */
function stubApi(
  onAudit: (url: URL) => Response = () => json([]),
  onAgents: () => Response = () => json(stations),
) {
  const auditCalls: URL[] = [];
  vi.spyOn(globalThis, "fetch").mockImplementation(
    vi.fn(async (input: RequestInfo | URL) => {
      const url = new URL(input.toString(), "http://x");
      if (url.pathname === "/api/v1/agents") return onAgents();
      if (url.pathname === "/api/v1/audit") {
        auditCalls.push(url);
        return onAudit(url);
      }
      throw new Error(`unexpected request: ${url.pathname}`);
    }),
  );
  return auditCalls;
}

function spanOf(url: URL): number {
  return (
    new Date(url.searchParams.get("end")!).getTime() -
    new Date(url.searchParams.get("start")!).getTime()
  );
}

function renderAuditPage() {
  return render(
    <MemoryRouter>
      <AuthContext.Provider
        value={{ token: "operator-token", username: "admin", setSession: vi.fn() }}
      >
        <AuditPage />
      </AuthContext.Provider>
    </MemoryRouter>,
  );
}

/**
 * The table row for an action name. Every known name is also an option of the
 * action filter, so the lookup is scoped to the table.
 */
async function rowOf(label: string): Promise<HTMLElement> {
  const table = await screen.findByRole("table");
  return within(table).getByText(label).closest("tr")!;
}

const apply = () => userEvent.click(screen.getByRole("button", { name: "Показать" }));

afterEach(() => {
  vi.restoreAllMocks();
});

describe("AuditPage query", () => {
  it("loads the last 24 hours ending now by default, with no actor or action", async () => {
    const auditCalls = stubApi();

    renderAuditPage();

    await waitFor(() => expect(auditCalls).toHaveLength(1));
    expect(spanOf(auditCalls[0])).toBe(24 * HOUR);
    const end = new Date(auditCalls[0].searchParams.get("end")!).getTime();
    expect(Math.abs(Date.now() - end)).toBeLessThan(5_000);
    expect(auditCalls[0].searchParams.has("actor")).toBe(false);
    expect(auditCalls[0].searchParams.has("action")).toBe(false);
    expect(auditCalls[0].searchParams.get("limit")).toBe(String(PAGE_SIZE));
  });

  it("sends the matching range for each preset", async () => {
    const auditCalls = stubApi();
    renderAuditPage();
    await waitFor(() => expect(auditCalls).toHaveLength(1));

    await userEvent.click(screen.getByRole("button", { name: "Последний час" }));
    await apply();
    await waitFor(() => expect(auditCalls).toHaveLength(2));
    expect(spanOf(auditCalls[1])).toBe(HOUR);

    await userEvent.click(screen.getByRole("button", { name: "Последние 7 дней" }));
    await apply();
    await waitFor(() => expect(auditCalls).toHaveLength(3));
    expect(spanOf(auditCalls[2])).toBe(7 * 24 * HOUR);
  });

  it("refuses a custom range whose end is not after its start, without a request", async () => {
    const auditCalls = stubApi();
    renderAuditPage();
    await waitFor(() => expect(auditCalls).toHaveLength(1));

    await userEvent.click(screen.getByRole("button", { name: "Свой период" }));
    fireEvent.change(screen.getByLabelText("Начало"), {
      target: { value: "2026-09-02T12:00" },
    });
    fireEvent.change(screen.getByLabelText("Конец"), {
      target: { value: "2026-09-01T12:00" },
    });
    await apply();

    expect(screen.getByText("Конец периода должен быть позже начала")).toBeInTheDocument();
    expect(auditCalls).toHaveLength(1);
  });

  it("sends a valid custom range as ISO instants", async () => {
    const auditCalls = stubApi();
    renderAuditPage();
    await waitFor(() => expect(auditCalls).toHaveLength(1));

    await userEvent.click(screen.getByRole("button", { name: "Свой период" }));
    fireEvent.change(screen.getByLabelText("Начало"), {
      target: { value: "2026-09-01T12:00" },
    });
    fireEvent.change(screen.getByLabelText("Конец"), {
      target: { value: "2026-09-01T13:00" },
    });
    await apply();

    await waitFor(() => expect(auditCalls).toHaveLength(2));
    expect(auditCalls[1].searchParams.get("start")).toBe(
      new Date("2026-09-01T12:00").toISOString(),
    );
    expect(auditCalls[1].searchParams.get("end")).toBe(
      new Date("2026-09-01T13:00").toISOString(),
    );
  });

  it("sends the typed actor, trimmed", async () => {
    const auditCalls = stubApi();
    renderAuditPage();
    await waitFor(() => expect(auditCalls).toHaveLength(1));

    await userEvent.type(screen.getByLabelText("Кто"), "  admin ");
    await apply();

    await waitFor(() => expect(auditCalls).toHaveLength(2));
    expect(auditCalls[1].searchParams.get("actor")).toBe("admin");
  });

  it("sends a bare group when a group is chosen", async () => {
    const auditCalls = stubApi();
    renderAuditPage();
    await waitFor(() => expect(auditCalls).toHaveLength(1));

    await userEvent.selectOptions(
      screen.getByLabelText("Действие"),
      screen.getByRole("option", { name: "Все действия операторов" }),
    );
    await apply();

    await waitFor(() => expect(auditCalls).toHaveLength(2));
    expect(auditCalls[1].searchParams.get("action")).toBe("operator");
  });

  it("sends the full code when a single action is chosen", async () => {
    const auditCalls = stubApi();
    renderAuditPage();
    await waitFor(() => expect(auditCalls).toHaveLength(1));

    await userEvent.selectOptions(
      screen.getByLabelText("Действие"),
      screen.getByRole("option", { name: "Неудачный вход оператора" }),
    );
    await apply();

    await waitFor(() => expect(auditCalls).toHaveLength(2));
    expect(auditCalls[1].searchParams.get("action")).toBe("operator.login_failed");
  });
});

describe("AuditPage rows", () => {
  it("shows the Russian action name, actor, target and details", async () => {
    stubApi(() =>
      json([
        entry(1, {
          actor: "admin",
          action: "agent.disabled",
          target: "some-target",
          detail: { hostname: "WS-01" },
        }),
      ]),
    );

    renderAuditPage();

    const row = await rowOf("Станция отключена");
    expect(within(row).getByText("admin")).toBeInTheDocument();
    expect(within(row).getByText("some-target")).toBeInTheDocument();
    expect(within(row).getByText("hostname: WS-01")).toBeInTheDocument();
    expect(within(row).getByTitle("agent.disabled")).toBeInTheDocument();
  });

  it("shows a dash for an entry with no details", async () => {
    stubApi(() => json([entry(1)]));

    renderAuditPage();

    const row = await rowOf("Вход оператора");
    expect(within(row).getByText("—")).toBeInTheDocument();
  });

  it("shows an unknown action as its raw code instead of hiding the entry", async () => {
    stubApi(() => json([entry(1, { action: "policy.changed_by_a_later_version" })]));

    renderAuditPage();

    expect(
      await screen.findByText("policy.changed_by_a_later_version"),
    ).toBeInTheDocument();
  });

  it("shows a station id as its hostname, keeping the id in the tooltip", async () => {
    stubApi(() =>
      json([entry(1, { actor: STATION_ID, action: "agent.report", target: STATION_ID })]),
    );

    renderAuditPage();

    const row = await rowOf("Получен отчёт за окно");
    expect(within(row).getAllByText("WS-01")).toHaveLength(2);
    expect(within(row).getAllByTitle(STATION_ID)).toHaveLength(2);
  });

  it("shows raw ids when the station list cannot be loaded", async () => {
    stubApi(
      () =>
        json([entry(1, { actor: STATION_ID, action: "agent.report", target: STATION_ID })]),
      () => json({ detail: "boom" }, 500),
    );

    renderAuditPage();

    const row = await rowOf("Получен отчёт за окно");
    expect(within(row).getAllByText(STATION_ID)).toHaveLength(2);
  });

  it("renders text that looks like markup literally, without creating elements", async () => {
    const hostile = "<img src=x onerror=alert(1)>";
    stubApi(() =>
      json([
        entry(1, {
          actor: hostile,
          action: "agent.enroll_rejected",
          target: "-",
          detail: { note: hostile },
        }),
      ]),
    );

    const { container } = renderAuditPage();

    const row = await rowOf("Отклонена регистрация станции");
    expect(within(row).getByText(hostile)).toBeInTheDocument();
    expect(within(row).getByText(`note: ${hostile}`)).toBeInTheDocument();
    expect(container.querySelector("img")).toBeNull();
  });
});

describe("AuditPage states", () => {
  it("shows an empty result as a message, not an error", async () => {
    stubApi(() => json([]));

    renderAuditPage();

    expect(await screen.findByText("За выбранный период записей нет.")).toBeInTheDocument();
    expect(screen.queryByText("Не удалось загрузить журнал")).not.toBeInTheDocument();
  });

  it("reports a failed request", async () => {
    stubApi(() => json({ detail: "boom" }, 500));

    renderAuditPage();

    expect(await screen.findByText("Не удалось загрузить журнал")).toBeInTheDocument();
  });

  it("always states what the log records and what it does not", async () => {
    stubApi();

    renderAuditPage();

    expect(
      screen.getByText(/просмотры собранных данных и самого журнала/),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        /Не фиксируются просмотр списка станций, политики и списка операторов/,
      ),
    ).toBeInTheDocument();
    expect(screen.getByText(/не защищён от правки/)).toBeInTheDocument();
  });

  it("no longer claims that reads are not recorded", async () => {
    stubApi();

    renderAuditPage();

    expect(screen.queryByText(/не чтение данных/)).not.toBeInTheDocument();
  });
});

describe("AuditPage paging", () => {
  const fullPage = () =>
    json(Array.from({ length: PAGE_SIZE }, (_, index) => entry(index)));

  it("offers the next page when a page comes back full, and fetches the next offset", async () => {
    const auditCalls = stubApi((url) =>
      url.searchParams.get("offset") ? json([entry(9999)]) : fullPage(),
    );
    renderAuditPage();

    await userEvent.click(await screen.findByRole("button", { name: "Показать ещё" }));

    await waitFor(() => expect(auditCalls).toHaveLength(2));
    expect(auditCalls[1].searchParams.get("offset")).toBe(String(PAGE_SIZE));
    await waitFor(() =>
      expect(
        screen.queryByRole("button", { name: "Показать ещё" }),
      ).not.toBeInTheDocument(),
    );
  });

  it("does not offer another page when a page is not full", async () => {
    stubApi(() => json([entry(1)]));

    renderAuditPage();

    await screen.findByText("Вход оператора");
    expect(screen.queryByRole("button", { name: "Показать ещё" })).not.toBeInTheDocument();
  });

  it("continues the query on screen, not what the form was edited to since", async () => {
    const auditCalls = stubApi(() => fullPage());
    renderAuditPage();
    await userEvent.type(screen.getByLabelText("Кто"), "admin");
    await apply();
    await waitFor(() => expect(auditCalls).toHaveLength(2));
    await screen.findByRole("button", { name: "Показать ещё" });

    await userEvent.clear(screen.getByLabelText("Кто"));
    await userEvent.type(screen.getByLabelText("Кто"), "someone-else");
    await userEvent.click(screen.getByRole("button", { name: "Показать ещё" }));

    await waitFor(() => expect(auditCalls).toHaveLength(3));
    expect(auditCalls[2].searchParams.get("actor")).toBe("admin");
    expect(auditCalls[2].searchParams.get("offset")).toBe(String(PAGE_SIZE));
    expect(auditCalls[2].searchParams.get("start")).toBe(
      auditCalls[1].searchParams.get("start"),
    );
  });
});
