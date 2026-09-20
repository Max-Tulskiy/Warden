import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ReportsPage } from "../../src/pages/ReportsPage";
import { AuthContext } from "../../src/state/authContext";

const HOUR = 3_600_000;
const PAGE_SIZE = 500;

const stations = ["WS-01", "WS-02", "WS-03"].map((hostname, index) => ({
  id: `a-${index + 1}`,
  hostname,
  os: "linux",
  status: "active",
  enrolled_at: "2026-08-01T00:00:00Z",
  last_seen_at: "2026-09-01T12:00:00Z",
}));

function fleetEvent(n: number, hostname = "WS-01", agentId = "a-1") {
  return {
    id: `e-${n}`,
    category: "processes",
    occurred_at: "2026-09-01T12:00:00Z",
    payload: { name: "app.exe", pid: n },
    agent_id: agentId,
    hostname,
  };
}

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status });
}

/** Stubs the two endpoints the page uses and records every report request. */
function stubApi(onEvents: (url: URL) => Response = () => json([])) {
  const eventCalls: URL[] = [];
  vi.spyOn(globalThis, "fetch").mockImplementation(
    vi.fn(async (input: RequestInfo | URL) => {
      const url = new URL(input.toString(), "http://x");
      if (url.pathname === "/api/v1/agents") return json(stations);
      if (url.pathname === "/api/v1/events") {
        eventCalls.push(url);
        return onEvents(url);
      }
      throw new Error(`unexpected request: ${url.pathname}`);
    }),
  );
  return eventCalls;
}

function spanOf(url: URL): number {
  return (
    new Date(url.searchParams.get("end")!).getTime() -
    new Date(url.searchParams.get("start")!).getTime()
  );
}

function renderReportsPage() {
  return render(
    <MemoryRouter>
      <AuthContext.Provider
        value={{ token: "operator-token", username: "admin", setSession: vi.fn() }}
      >
        <ReportsPage />
      </AuthContext.Provider>
    </MemoryRouter>,
  );
}

const apply = () => userEvent.click(screen.getByRole("button", { name: "Показать" }));

afterEach(() => {
  vi.restoreAllMocks();
});

describe("ReportsPage", () => {
  it("loads the last 24 hours ending now by default", async () => {
    const eventCalls = stubApi();

    renderReportsPage();

    await waitFor(() => expect(eventCalls).toHaveLength(1));
    expect(spanOf(eventCalls[0])).toBe(24 * HOUR);
    const end = new Date(eventCalls[0].searchParams.get("end")!).getTime();
    expect(Math.abs(Date.now() - end)).toBeLessThan(5_000);
  });

  it("sends the matching range for each preset", async () => {
    const eventCalls = stubApi();
    renderReportsPage();
    await waitFor(() => expect(eventCalls).toHaveLength(1));

    await userEvent.click(screen.getByRole("button", { name: "Последний час" }));
    await apply();
    await waitFor(() => expect(eventCalls).toHaveLength(2));
    expect(spanOf(eventCalls[1])).toBe(HOUR);

    await userEvent.click(screen.getByRole("button", { name: "Последние 7 дней" }));
    await apply();
    await waitFor(() => expect(eventCalls).toHaveLength(3));
    expect(spanOf(eventCalls[2])).toBe(7 * 24 * HOUR);
  });

  it("refuses a custom range whose end is not after its start, without a request", async () => {
    const eventCalls = stubApi();
    renderReportsPage();
    await waitFor(() => expect(eventCalls).toHaveLength(1));

    await userEvent.click(screen.getByRole("button", { name: "Свой период" }));
    fireEvent.change(screen.getByLabelText("Начало"), {
      target: { value: "2026-09-02T12:00" },
    });
    fireEvent.change(screen.getByLabelText("Конец"), {
      target: { value: "2026-09-01T12:00" },
    });
    await apply();

    expect(
      await screen.findByText("Конец периода должен быть позже начала"),
    ).toBeInTheDocument();
    expect(eventCalls).toHaveLength(1);
  });

  it("sends a valid custom range as ISO instants", async () => {
    const eventCalls = stubApi();
    renderReportsPage();
    await waitFor(() => expect(eventCalls).toHaveLength(1));

    await userEvent.click(screen.getByRole("button", { name: "Свой период" }));
    fireEvent.change(screen.getByLabelText("Начало"), {
      target: { value: "2026-09-01T09:00" },
    });
    fireEvent.change(screen.getByLabelText("Конец"), {
      target: { value: "2026-09-08T09:00" },
    });
    await apply();

    await waitFor(() => expect(eventCalls).toHaveLength(2));
    expect(eventCalls[1].searchParams.get("start")).toBe(
      new Date("2026-09-01T09:00").toISOString(),
    );
    expect(eventCalls[1].searchParams.get("end")).toBe(
      new Date("2026-09-08T09:00").toISOString(),
    );
  });

  it("sends one agent_id per ticked station", async () => {
    const eventCalls = stubApi();
    renderReportsPage();
    await waitFor(() => expect(eventCalls).toHaveLength(1));
    expect(eventCalls[0].searchParams.has("agent_id")).toBe(false);

    await userEvent.click(await screen.findByRole("checkbox", { name: "WS-01" }));
    await userEvent.click(screen.getByRole("checkbox", { name: "WS-03" }));
    await apply();

    await waitFor(() => expect(eventCalls).toHaveLength(2));
    expect(eventCalls[1].searchParams.getAll("agent_id")).toEqual(["a-1", "a-3"]);
  });

  it("sends the chosen category", async () => {
    const eventCalls = stubApi();
    renderReportsPage();
    await waitFor(() => expect(eventCalls).toHaveLength(1));

    await userEvent.selectOptions(screen.getByLabelText("Категория"), "Печать");
    await apply();

    await waitFor(() => expect(eventCalls).toHaveLength(2));
    expect(eventCalls[1].searchParams.get("category")).toBe("printing");
  });

  it("labels every row with its station, linking to that station", async () => {
    stubApi(() => json([fleetEvent(1, "WS-02", "a-2")]));

    renderReportsPage();

    const link = await screen.findByRole("link", { name: "WS-02" });
    expect(link).toHaveAttribute("href", "/agents/a-2");
    expect(screen.getByRole("columnheader", { name: "Станция" })).toBeInTheDocument();
  });

  it("shows an empty result as a message, not an error", async () => {
    stubApi(() => json([]));

    renderReportsPage();

    expect(await screen.findByText("За выбранный период данных нет.")).toBeInTheDocument();
    expect(screen.queryByText("Не удалось загрузить отчёт")).not.toBeInTheDocument();
  });

  it("always states that only window-delivered events are shown", () => {
    stubApi();

    renderReportsPage();

    expect(
      screen.getByText(
        /Показаны только события, которые станции передали по запросам окна/,
      ),
    ).toBeInTheDocument();
  });

  it("offers the next page when a page comes back full", async () => {
    const eventCalls = stubApi((url) =>
      url.searchParams.get("offset") === String(PAGE_SIZE)
        ? json([fleetEvent(PAGE_SIZE + 1)])
        : json(Array.from({ length: PAGE_SIZE }, (_, index) => fleetEvent(index + 1))),
    );
    renderReportsPage();

    await userEvent.click(await screen.findByRole("button", { name: "Показать ещё" }));

    await waitFor(() => expect(eventCalls).toHaveLength(2));
    expect(eventCalls[1].searchParams.get("offset")).toBe(String(PAGE_SIZE));
    expect(eventCalls[1].searchParams.get("limit")).toBe(String(PAGE_SIZE));
    await waitFor(() =>
      expect(
        screen.queryByRole("button", { name: "Показать ещё" }),
      ).not.toBeInTheDocument(),
    );
  });

  it("reports a failed request", async () => {
    stubApi(() => json({ detail: "boom" }, 500));

    renderReportsPage();

    expect(await screen.findByText("Не удалось загрузить отчёт")).toBeInTheDocument();
  });
});
