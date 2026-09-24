import { afterEach, describe, expect, it, vi } from "vitest";

import {
  ApiError,
  changePassword,
  getEvents,
  getFleetEvents,
  getInventoryChanges,
  getPolicy,
  listAudit,
  setAgentStatus,
} from "../../src/api/client";

afterEach(() => {
  vi.restoreAllMocks();
});

function mockFetch(response: Response) {
  return vi.spyOn(globalThis, "fetch").mockResolvedValue(response);
}

describe("getFleetEvents", () => {
  const range = { start: "2026-09-01T12:00:00.000Z", end: "2026-09-01T13:00:00.000Z" };

  it("sends the range and the bearer token", async () => {
    const fetchMock = mockFetch(new Response(JSON.stringify([]), { status: 200 }));

    await getFleetEvents("operator-token", range);

    const [input, init] = fetchMock.mock.calls[0];
    const url = new URL(input.toString(), "http://x");
    expect(url.pathname).toBe("/api/v1/events");
    expect(url.searchParams.get("start")).toBe(range.start);
    expect(url.searchParams.get("end")).toBe(range.end);
    expect(url.searchParams.has("agent_id")).toBe(false);
    expect(url.searchParams.has("category")).toBe(false);
    expect(init?.headers).toMatchObject({ Authorization: "Bearer operator-token" });
  });

  it("repeats agent_id once per selected station and passes category and paging", async () => {
    const fetchMock = mockFetch(new Response(JSON.stringify([]), { status: 200 }));

    await getFleetEvents(
      "token",
      { ...range, agentIds: ["a-1", "a-2"], category: "printing" },
      { limit: 500, offset: 1000 },
    );

    const url = new URL(fetchMock.mock.calls[0][0].toString(), "http://x");
    expect(url.searchParams.getAll("agent_id")).toEqual(["a-1", "a-2"]);
    expect(url.searchParams.get("category")).toBe("printing");
    expect(url.searchParams.get("limit")).toBe("500");
    expect(url.searchParams.get("offset")).toBe("1000");
  });
});

describe("listAudit", () => {
  const range = { start: "2026-09-01T12:00:00.000Z", end: "2026-09-01T13:00:00.000Z" };

  it("sends the range and the bearer token to /audit", async () => {
    const fetchMock = mockFetch(new Response(JSON.stringify([]), { status: 200 }));

    await listAudit("operator-token", range);

    const [input, init] = fetchMock.mock.calls[0];
    const url = new URL(input.toString(), "http://x");
    expect(url.pathname).toBe("/api/v1/audit");
    expect(url.searchParams.get("start")).toBe(range.start);
    expect(url.searchParams.get("end")).toBe(range.end);
    expect(init?.headers).toMatchObject({ Authorization: "Bearer operator-token" });
  });

  it("omits actor, action and paging when they are not set", async () => {
    const fetchMock = mockFetch(new Response(JSON.stringify([]), { status: 200 }));

    await listAudit("token", range);

    const url = new URL(fetchMock.mock.calls[0][0].toString(), "http://x");
    expect(url.searchParams.has("actor")).toBe(false);
    expect(url.searchParams.has("action")).toBe(false);
    expect(url.searchParams.has("limit")).toBe(false);
    expect(url.searchParams.has("offset")).toBe(false);
  });

  it("passes actor, action and paging through", async () => {
    const fetchMock = mockFetch(new Response(JSON.stringify([]), { status: 200 }));

    await listAudit(
      "token",
      { ...range, actor: "admin", action: "operator.login" },
      { limit: 500, offset: 1000 },
    );

    const url = new URL(fetchMock.mock.calls[0][0].toString(), "http://x");
    expect(url.searchParams.get("actor")).toBe("admin");
    expect(url.searchParams.get("action")).toBe("operator.login");
    expect(url.searchParams.get("limit")).toBe("500");
    expect(url.searchParams.get("offset")).toBe("1000");
  });

  it("surfaces an expired session as an ApiError carrying the status", async () => {
    mockFetch(
      new Response(JSON.stringify({ detail: "Invalid or missing credentials" }), {
        status: 401,
      }),
    );

    await expect(listAudit("token", range)).rejects.toMatchObject({
      name: "Error",
      status: 401,
    });
  });
});

describe("getPolicy", () => {
  it("reads the policy with the bearer token", async () => {
    const policy = { max_request_window_hours: 4 };
    const fetchMock = mockFetch(new Response(JSON.stringify(policy), { status: 200 }));

    const result = await getPolicy("token");

    expect(fetchMock.mock.calls[0][0].toString()).toBe("/api/v1/policy");
    expect(result).toEqual(policy);
  });
});

describe("changePassword", () => {
  it("posts both passwords and resolves on 204", async () => {
    const fetchMock = mockFetch(new Response(null, { status: 204 }));

    await expect(
      changePassword("token", "old-pass", "new-pass-123"),
    ).resolves.toBeUndefined();

    const [input, init] = fetchMock.mock.calls[0];
    expect(input.toString()).toBe("/api/v1/auth/password");
    expect(init?.method).toBe("POST");
    expect(JSON.parse(init?.body as string)).toEqual({
      current_password: "old-pass",
      new_password: "new-pass-123",
    });
  });

  it("surfaces a rejected password as an ApiError carrying the status", async () => {
    mockFetch(
      new Response(JSON.stringify({ detail: "Current password is incorrect" }), {
        status: 400,
      }),
    );

    const failure = await changePassword("token", "wrong", "new-pass-123").catch(
      (error: unknown) => error,
    );

    expect(failure).toBeInstanceOf(ApiError);
    expect((failure as ApiError).status).toBe(400);
  });
});

describe("setAgentStatus", () => {
  it("sends PATCH with the new status and returns the updated station", async () => {
    const station = { id: "a-1", status: "disabled" };
    const fetchMock = mockFetch(new Response(JSON.stringify(station), { status: 200 }));

    const result = await setAgentStatus("token", "a-1", "disabled");

    const [input, init] = fetchMock.mock.calls[0];
    expect(input.toString()).toBe("/api/v1/agents/a-1");
    expect(init?.method).toBe("PATCH");
    expect(JSON.parse(init?.body as string)).toEqual({ status: "disabled" });
    expect(result).toEqual(station);
  });
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
