import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { getPolicy, listOperators } from "../../src/api/client";
import { AuthProvider } from "../../src/state/auth";
import { useAuth } from "../../src/state/authContext";

function Probe() {
  const { token, username, role, sessionEnded, setSession } = useAuth();
  return (
    <div>
      <p data-testid="token">{token ?? "none"}</p>
      <p data-testid="username">{username ?? "none"}</p>
      <p data-testid="role">{role ?? "none"}</p>
      <p data-testid="ended">{String(sessionEnded)}</p>
      <button onClick={() => setSession({ token: "t-1", username: "admin" })}>
        sign in
      </button>
      <button onClick={() => setSession(null)}>sign out</button>
    </div>
  );
}

type Reply = Response | Promise<Response>;

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status });

/**
 * Stubs the server. `/auth/me` answers with `me()`, defaulting to an
 * administrator; every other path is refused with `otherStatus`, which is what
 * an ended session (401) or a missing role (403) looks like to the client.
 */
function stubApi(options: { me?: () => Reply; otherStatus?: number } = {}) {
  const meCalls = { count: 0 };
  vi.spyOn(globalThis, "fetch").mockImplementation(
    vi.fn(async (input: RequestInfo | URL) => {
      const path = new URL(input.toString(), "http://x").pathname;
      if (path === "/api/v1/auth/me") {
        meCalls.count += 1;
        return options.me?.() ?? json({ username: "admin", role: "admin" });
      }
      return json({ detail: "refused" }, options.otherStatus ?? 401);
    }),
  );
  return meCalls;
}

const refusedRequest = () => act(() => getPolicy("t-1").catch(() => undefined));

beforeEach(() => {
  window.localStorage.clear();
});

afterEach(() => {
  vi.restoreAllMocks();
});

function renderProvider() {
  return render(
    <AuthProvider>
      <Probe />
    </AuthProvider>,
  );
}

describe("AuthProvider session", () => {
  it("starts with no ended session", () => {
    stubApi();
    renderProvider();

    expect(screen.getByTestId("ended")).toHaveTextContent("false");
  });

  it("clears the session and marks it ended when the server refuses a request", async () => {
    stubApi();
    renderProvider();
    await userEvent.click(screen.getByText("sign in"));
    expect(screen.getByTestId("token")).toHaveTextContent("t-1");

    await refusedRequest();

    expect(screen.getByTestId("token")).toHaveTextContent("none");
    expect(screen.getByTestId("username")).toHaveTextContent("none");
    expect(screen.getByTestId("ended")).toHaveTextContent("true");
    expect(window.localStorage.getItem("warden.token")).toBeNull();
    expect(window.localStorage.getItem("warden.username")).toBeNull();
  });

  it("ends in the same state when several requests are refused in a row", async () => {
    stubApi();
    renderProvider();
    await userEvent.click(screen.getByText("sign in"));

    await refusedRequest();
    await refusedRequest();
    await refusedRequest();

    expect(screen.getByTestId("token")).toHaveTextContent("none");
    expect(screen.getByTestId("ended")).toHaveTextContent("true");
  });

  it("forgets that a session ended once the operator signs in again", async () => {
    stubApi();
    renderProvider();
    await userEvent.click(screen.getByText("sign in"));
    await refusedRequest();
    expect(screen.getByTestId("ended")).toHaveTextContent("true");

    await userEvent.click(screen.getByText("sign in"));

    expect(screen.getByTestId("ended")).toHaveTextContent("false");
    expect(screen.getByTestId("token")).toHaveTextContent("t-1");
  });

  it("does not call a voluntary sign-out an ended session", async () => {
    stubApi();
    renderProvider();
    await userEvent.click(screen.getByText("sign in"));

    await userEvent.click(screen.getByText("sign out"));

    expect(screen.getByTestId("token")).toHaveTextContent("none");
    expect(screen.getByTestId("ended")).toHaveTextContent("false");
  });

  it("stops listening for refused requests when it is unmounted", async () => {
    stubApi();
    window.localStorage.setItem("warden.token", "t-1");
    window.localStorage.setItem("warden.username", "admin");
    const { unmount } = renderProvider();

    unmount();
    await refusedRequest();

    expect(window.localStorage.getItem("warden.token")).toBe("t-1");
  });
});

describe("AuthProvider role", () => {
  it("loads the role of a session that was already stored", async () => {
    stubApi({ me: () => json({ username: "watcher", role: "viewer" }) });
    window.localStorage.setItem("warden.token", "t-1");
    window.localStorage.setItem("warden.username", "watcher");

    renderProvider();

    await waitFor(() => expect(screen.getByTestId("role")).toHaveTextContent("viewer"));
  });

  it("loads the role after signing in", async () => {
    stubApi();
    renderProvider();
    expect(screen.getByTestId("role")).toHaveTextContent("none");

    await userEvent.click(screen.getByText("sign in"));

    await waitFor(() => expect(screen.getByTestId("role")).toHaveTextContent("admin"));
  });

  it("asks nothing and has no role when nobody is signed in", async () => {
    const meCalls = stubApi();

    renderProvider();

    expect(screen.getByTestId("role")).toHaveTextContent("none");
    expect(meCalls.count).toBe(0);
  });

  it("forgets the role on sign-out", async () => {
    stubApi();
    renderProvider();
    await userEvent.click(screen.getByText("sign in"));
    await waitFor(() => expect(screen.getByTestId("role")).toHaveTextContent("admin"));

    await userEvent.click(screen.getByText("sign out"));

    expect(screen.getByTestId("role")).toHaveTextContent("none");
  });

  it("does not let a slow answer give a signed-out person a role", async () => {
    let release: (reply: Response) => void = () => undefined;
    const held = new Promise<Response>((resolve) => {
      release = resolve;
    });
    stubApi({ me: () => held });
    renderProvider();
    await userEvent.click(screen.getByText("sign in"));
    await userEvent.click(screen.getByText("sign out"));

    await act(async () => release(json({ username: "admin", role: "admin" })));

    expect(screen.getByTestId("role")).toHaveTextContent("none");
  });

  it("reloads the role when the server says an action is forbidden", async () => {
    let role = "admin";
    stubApi({ me: () => json({ username: "admin", role }), otherStatus: 403 });
    renderProvider();
    await userEvent.click(screen.getByText("sign in"));
    await waitFor(() => expect(screen.getByTestId("role")).toHaveTextContent("admin"));

    role = "viewer"; // demoted by another administrator in the meantime
    await act(() => listOperators("t-1").catch(() => undefined));

    await waitFor(() => expect(screen.getByTestId("role")).toHaveTextContent("viewer"));
    expect(screen.getByTestId("token")).toHaveTextContent("t-1");
    expect(screen.getByTestId("ended")).toHaveTextContent("false");
  });

  it("keeps the session and has no role when the role cannot be loaded", async () => {
    stubApi({ me: () => json({ detail: "boom" }, 500) });
    renderProvider();

    await userEvent.click(screen.getByText("sign in"));

    await waitFor(() => expect(screen.getByTestId("token")).toHaveTextContent("t-1"));
    expect(screen.getByTestId("role")).toHaveTextContent("none");
    expect(screen.getByTestId("ended")).toHaveTextContent("false");
  });
});
