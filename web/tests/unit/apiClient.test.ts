import { afterEach, describe, expect, it, vi } from "vitest";

import {
  ApiError,
  changePassword,
  createOperator,
  getEvents,
  getFleetEvents,
  getInventoryChanges,
  getMe,
  getPolicy,
  listAudit,
  listOperators,
  login,
  logoutAll,
  resetOperatorPassword,
  setAgentStatus,
  setForbiddenHandler,
  setUnauthorizedHandler,
  updateOperator,
} from "../../src/api/client";

afterEach(() => {
  vi.restoreAllMocks();
  setUnauthorizedHandler(null);
  setForbiddenHandler(null);
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
  it("posts both passwords and resolves to the token of the session it keeps", async () => {
    const fetchMock = mockFetch(
      new Response(JSON.stringify({ access_token: "new-token", token_type: "bearer" }), {
        status: 200,
      }),
    );

    await expect(changePassword("token", "old-pass", "new-pass-123")).resolves.toBe(
      "new-token",
    );

    const [input, init] = fetchMock.mock.calls[0];
    expect(input.toString()).toBe("/api/v1/auth/password");
    expect(init?.method).toBe("POST");
    expect(init?.headers).toMatchObject({ Authorization: "Bearer token" });
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

describe("logoutAll", () => {
  it("posts to logout-all with the bearer token and resolves on 204", async () => {
    const fetchMock = mockFetch(new Response(null, { status: 204 }));

    await expect(logoutAll("token")).resolves.toBeUndefined();

    const [input, init] = fetchMock.mock.calls[0];
    expect(input.toString()).toBe("/api/v1/auth/logout-all");
    expect(init?.method).toBe("POST");
    expect(init?.headers).toMatchObject({ Authorization: "Bearer token" });
  });
});

describe("the unauthorized handler", () => {
  const refused = () =>
    new Response(JSON.stringify({ detail: "Invalid or missing credentials" }), {
      status: 401,
    });

  it("is called once when a request that carried a token is refused, which still throws", async () => {
    const handler = vi.fn();
    setUnauthorizedHandler(handler);
    mockFetch(refused());

    const failure = await getPolicy("token").catch((error: unknown) => error);

    expect(handler).toHaveBeenCalledTimes(1);
    expect(failure).toBeInstanceOf(ApiError);
    expect((failure as ApiError).status).toBe(401);
  });

  it("is not called when a sign-in with a wrong password is refused", async () => {
    const handler = vi.fn();
    setUnauthorizedHandler(handler);
    mockFetch(
      new Response(JSON.stringify({ detail: "Invalid username or password" }), {
        status: 401,
      }),
    );

    await expect(login("admin", "wrong")).rejects.toBeInstanceOf(ApiError);

    expect(handler).not.toHaveBeenCalled();
  });

  it.each([400, 403, 404, 429, 500])("is not called for a %i", async (status) => {
    const handler = vi.fn();
    setUnauthorizedHandler(handler);
    mockFetch(new Response(JSON.stringify({ detail: "nope" }), { status }));

    await expect(getPolicy("token")).rejects.toBeInstanceOf(ApiError);

    expect(handler).not.toHaveBeenCalled();
  });

  it("is not called after it has been cleared", async () => {
    const handler = vi.fn();
    setUnauthorizedHandler(handler);
    setUnauthorizedHandler(null);
    mockFetch(refused());

    await expect(getPolicy("token")).rejects.toBeInstanceOf(ApiError);

    expect(handler).not.toHaveBeenCalled();
  });

  it("does not fire for a successful response", async () => {
    const handler = vi.fn();
    setUnauthorizedHandler(handler);
    mockFetch(new Response(JSON.stringify({}), { status: 200 }));

    await getPolicy("token");

    expect(handler).not.toHaveBeenCalled();
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

describe("getMe", () => {
  it("reads who is signed in with the bearer token", async () => {
    const me = { username: "admin", role: "admin" };
    const fetchMock = mockFetch(new Response(JSON.stringify(me), { status: 200 }));

    await expect(getMe("token")).resolves.toEqual(me);

    const [input, init] = fetchMock.mock.calls[0];
    expect(input.toString()).toBe("/api/v1/auth/me");
    expect(init?.headers).toMatchObject({ Authorization: "Bearer token" });
  });
});

describe("operator management", () => {
  const account = { id: "o-1", username: "colleague", role: "viewer", status: "active" };

  it("lists the accounts", async () => {
    const fetchMock = mockFetch(new Response(JSON.stringify([account]), { status: 200 }));

    await expect(listOperators("token")).resolves.toEqual([account]);

    expect(fetchMock.mock.calls[0][0].toString()).toBe("/api/v1/operators");
  });

  it("creates an account by posting the username, role and password", async () => {
    const fetchMock = mockFetch(new Response(JSON.stringify(account), { status: 201 }));

    await expect(
      createOperator("token", {
        username: "colleague",
        role: "viewer",
        password: "long-enough-password",
      }),
    ).resolves.toEqual(account);

    const [input, init] = fetchMock.mock.calls[0];
    expect(input.toString()).toBe("/api/v1/operators");
    expect(init?.method).toBe("POST");
    expect(JSON.parse(init?.body as string)).toEqual({
      username: "colleague",
      role: "viewer",
      password: "long-enough-password",
    });
  });

  it("updates an account with only the fields it was given", async () => {
    const fetchMock = mockFetch(
      new Response(JSON.stringify({ ...account, role: "admin" }), { status: 200 }),
    );

    await updateOperator("token", "o-1", { role: "admin" });

    const [input, init] = fetchMock.mock.calls[0];
    expect(input.toString()).toBe("/api/v1/operators/o-1");
    expect(init?.method).toBe("PATCH");
    expect(JSON.parse(init?.body as string)).toEqual({ role: "admin" });
  });

  it("resets a password by posting only the new one, and resolves on 204", async () => {
    const fetchMock = mockFetch(new Response(null, { status: 204 }));

    await expect(
      resetOperatorPassword("token", "o-1", "another-long-passphrase"),
    ).resolves.toBeUndefined();

    const [input, init] = fetchMock.mock.calls[0];
    expect(input.toString()).toBe("/api/v1/operators/o-1/password");
    expect(init?.method).toBe("POST");
    expect(JSON.parse(init?.body as string)).toEqual({
      new_password: "another-long-passphrase",
    });
  });

  it("surfaces a duplicate name as an ApiError carrying the 409", async () => {
    mockFetch(new Response(JSON.stringify({ detail: "exists" }), { status: 409 }));

    const failure = await createOperator("token", {
      username: "colleague",
      role: "viewer",
      password: "long-enough-password",
    }).catch((error: unknown) => error);

    expect(failure).toBeInstanceOf(ApiError);
    expect((failure as ApiError).status).toBe(409);
  });
});

describe("the forbidden handler", () => {
  const refused = (status: number) =>
    new Response(JSON.stringify({ detail: "Administrator role required" }), { status });

  it("is called once when a request that carried a token is forbidden, which still throws", async () => {
    const handler = vi.fn();
    setForbiddenHandler(handler);
    mockFetch(refused(403));

    const failure = await listOperators("token").catch((error: unknown) => error);

    expect(handler).toHaveBeenCalledTimes(1);
    expect(failure).toBeInstanceOf(ApiError);
    expect((failure as ApiError).status).toBe(403);
  });

  it("is not called for a 403 that carried no token", async () => {
    const handler = vi.fn();
    setForbiddenHandler(handler);
    mockFetch(refused(403));

    await expect(login("admin", "pw")).rejects.toBeInstanceOf(ApiError);

    expect(handler).not.toHaveBeenCalled();
  });

  it.each([401, 404, 409, 422, 500])("is not called for a %i", async (status) => {
    const handler = vi.fn();
    setForbiddenHandler(handler);
    mockFetch(refused(status));

    await expect(listOperators("token")).rejects.toBeInstanceOf(ApiError);

    expect(handler).not.toHaveBeenCalled();
  });

  it("does not fire for a successful response, or after it has been cleared", async () => {
    const handler = vi.fn();
    setForbiddenHandler(handler);
    mockFetch(new Response(JSON.stringify([]), { status: 200 }));
    await listOperators("token");
    setForbiddenHandler(null);
    mockFetch(refused(403));
    await listOperators("token").catch(() => undefined);

    expect(handler).not.toHaveBeenCalled();
  });

  it("does not disturb the unauthorized handler", async () => {
    const forbidden = vi.fn();
    const unauthorized = vi.fn();
    setForbiddenHandler(forbidden);
    setUnauthorizedHandler(unauthorized);
    mockFetch(refused(401));

    await listOperators("token").catch(() => undefined);

    expect(unauthorized).toHaveBeenCalledTimes(1);
    expect(forbidden).not.toHaveBeenCalled();
  });
});
