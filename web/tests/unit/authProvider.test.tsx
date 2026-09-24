import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { getPolicy } from "../../src/api/client";
import { AuthProvider } from "../../src/state/auth";
import { useAuth } from "../../src/state/authContext";

function Probe() {
  const { token, username, sessionEnded, setSession } = useAuth();
  return (
    <div>
      <p data-testid="token">{token ?? "none"}</p>
      <p data-testid="username">{username ?? "none"}</p>
      <p data-testid="ended">{String(sessionEnded)}</p>
      <button onClick={() => setSession({ token: "t-1", username: "admin" })}>
        sign in
      </button>
      <button onClick={() => setSession(null)}>sign out</button>
    </div>
  );
}

const refuseEverything = () =>
  vi.spyOn(globalThis, "fetch").mockImplementation(
    async () =>
      new Response(JSON.stringify({ detail: "Invalid or missing credentials" }), {
        status: 401,
      }),
  );

/** A panel request the server refuses, as it does for an ended session. */
const refusedRequest = () => act(() => getPolicy("t-1").catch(() => undefined));

beforeEach(() => {
  window.localStorage.clear();
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("AuthProvider", () => {
  it("starts with no ended session", () => {
    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    );

    expect(screen.getByTestId("ended")).toHaveTextContent("false");
  });

  it("clears the session and marks it ended when the server refuses a request", async () => {
    refuseEverything();
    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    );
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
    refuseEverything();
    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    );
    await userEvent.click(screen.getByText("sign in"));

    await refusedRequest();
    await refusedRequest();
    await refusedRequest();

    expect(screen.getByTestId("token")).toHaveTextContent("none");
    expect(screen.getByTestId("ended")).toHaveTextContent("true");
  });

  it("forgets that a session ended once the operator signs in again", async () => {
    refuseEverything();
    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    );
    await userEvent.click(screen.getByText("sign in"));
    await refusedRequest();
    expect(screen.getByTestId("ended")).toHaveTextContent("true");

    await userEvent.click(screen.getByText("sign in"));

    expect(screen.getByTestId("ended")).toHaveTextContent("false");
    expect(screen.getByTestId("token")).toHaveTextContent("t-1");
  });

  it("does not call a voluntary sign-out an ended session", async () => {
    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    );
    await userEvent.click(screen.getByText("sign in"));

    await userEvent.click(screen.getByText("sign out"));

    expect(screen.getByTestId("token")).toHaveTextContent("none");
    expect(screen.getByTestId("ended")).toHaveTextContent("false");
  });

  it("stops listening for refused requests when it is unmounted", async () => {
    refuseEverything();
    window.localStorage.setItem("warden.token", "t-1");
    window.localStorage.setItem("warden.username", "admin");
    const { unmount } = render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    );

    unmount();
    await refusedRequest();

    expect(window.localStorage.getItem("warden.token")).toBe("t-1");
  });
});
