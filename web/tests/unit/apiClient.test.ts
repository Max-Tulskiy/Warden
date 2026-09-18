import { afterEach, describe, expect, it, vi } from "vitest";

import { getEvents, getInventoryChanges } from "../../src/api/client";

afterEach(() => {
  vi.restoreAllMocks();
});

describe("api client pagination", () => {
  it("omits limit/offset from getEvents when not given", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(new Response(JSON.stringify([]), { status: 200 }));

    await getEvents("token", "agent-1", "2026-01-01");

    const url = fetchMock.mock.calls[0][0]!.toString();
    expect(url).toBe("/api/v1/agents/agent-1/events?report_date=2026-01-01");
  });

  it("passes limit and offset through to getEvents", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(new Response(JSON.stringify([]), { status: 200 }));

    await getEvents("token", "agent-1", "2026-01-01", { limit: 50, offset: 100 });

    const url = new URL(fetchMock.mock.calls[0][0]!.toString(), "http://x");
    expect(url.searchParams.get("report_date")).toBe("2026-01-01");
    expect(url.searchParams.get("limit")).toBe("50");
    expect(url.searchParams.get("offset")).toBe("100");
  });

  it("passes limit and offset through to getInventoryChanges", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(new Response(JSON.stringify([]), { status: 200 }));

    await getInventoryChanges("token", "agent-1", { limit: 10, offset: 20 });

    const url = new URL(fetchMock.mock.calls[0][0]!.toString(), "http://x");
    expect(url.pathname).toBe("/api/v1/agents/agent-1/inventory/changes");
    expect(url.searchParams.get("limit")).toBe("10");
    expect(url.searchParams.get("offset")).toBe("20");
  });

  it("omits the query string entirely for getInventoryChanges when unpaginated", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(new Response(JSON.stringify([]), { status: 200 }));

    await getInventoryChanges("token", "agent-1");

    const url = fetchMock.mock.calls[0][0]!.toString();
    expect(url).toBe("/api/v1/agents/agent-1/inventory/changes");
  });
});
