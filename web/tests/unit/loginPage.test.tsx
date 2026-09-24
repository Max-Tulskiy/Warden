import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { LoginPage } from "../../src/pages/LoginPage";
import { AuthContext } from "../../src/state/authContext";

const ENDED = "Сеанс завершён. Войдите снова.";

function renderLogin(options: { sessionEnded?: boolean; setSession?: () => void } = {}) {
  const setSession = options.setSession ?? vi.fn();
  render(
    <MemoryRouter initialEntries={["/login"]}>
      <AuthContext.Provider
        value={{
          token: null,
          username: null,
          sessionEnded: options.sessionEnded,
          setSession,
        }}
      >
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/agents" element={<p>agents page</p>} />
        </Routes>
      </AuthContext.Provider>
    </MemoryRouter>,
  );
  return setSession;
}

async function submit(password = "correct-password") {
  await userEvent.type(screen.getByLabelText("Имя пользователя"), "admin");
  await userEvent.type(screen.getByLabelText("Пароль"), password);
  await userEvent.click(screen.getByRole("button", { name: "Войти" }));
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("LoginPage", () => {
  it("tells the operator the session ended when the server refused it", () => {
    renderLogin({ sessionEnded: true });

    expect(screen.getByRole("status")).toHaveTextContent(ENDED);
  });

  it("shows no such message on an ordinary visit", () => {
    renderLogin({ sessionEnded: false });

    expect(screen.queryByText(ENDED)).not.toBeInTheDocument();
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("shows no such message when the flag is absent", () => {
    renderLogin();

    expect(screen.queryByText(ENDED)).not.toBeInTheDocument();
  });

  it("stores the session and moves on after a successful sign-in", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ access_token: "issued-token" }), { status: 200 }),
    );
    const setSession = renderLogin({ sessionEnded: true });

    await submit();

    await waitFor(() =>
      expect(setSession).toHaveBeenCalledWith({ token: "issued-token", username: "admin" }),
    );
    expect(await screen.findByText("agents page")).toBeInTheDocument();
  });

  it("keeps the notice next to the usual message after a wrong password", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ detail: "Invalid username or password" }), {
        status: 401,
      }),
    );
    const setSession = renderLogin({ sessionEnded: true });

    await submit("wrong-password");

    expect(
      await screen.findByText("Неверное имя пользователя или пароль"),
    ).toBeInTheDocument();
    expect(screen.getByText(ENDED)).toBeInTheDocument();
    expect(setSession).not.toHaveBeenCalled();
  });
});
