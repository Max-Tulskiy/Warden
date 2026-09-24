import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Operator } from "../../src/api/types";
import { OperatorsPage } from "../../src/pages/OperatorsPage";
import { AuthContext } from "../../src/state/authContext";

const PASSWORD = "a-long-enough-passphrase";

const initial = (): Operator[] => [
  { id: "o-0", username: "admin", role: "admin", status: "active" },
  { id: "o-1", username: "watcher", role: "viewer", status: "active" },
  { id: "o-2", username: "second", role: "admin", status: "active" },
  { id: "o-3", username: "gone", role: "viewer", status: "disabled" },
];

interface Overrides {
  list?: () => Response;
  create?: () => Response;
  patch?: () => Response;
  reset?: () => Response;
}

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status });

/** A tiny in-memory server for the four account endpoints, recording the writes. */
function stubApi(overrides: Overrides = {}) {
  let accounts = initial();
  const calls = {
    create: [] as Record<string, unknown>[],
    patch: [] as { id: string; body: Record<string, unknown> }[],
    reset: [] as { id: string; body: Record<string, unknown> }[],
  };
  vi.spyOn(globalThis, "fetch").mockImplementation(
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = new URL(input.toString(), "http://x").pathname;
      const method = init?.method ?? "GET";
      const body = init?.body ? JSON.parse(init.body as string) : undefined;

      if (path === "/api/v1/operators" && method === "GET") {
        return overrides.list?.() ?? json(accounts);
      }
      if (path === "/api/v1/operators" && method === "POST") {
        calls.create.push(body);
        if (overrides.create) return overrides.create();
        const created: Operator = {
          id: `o-${accounts.length}`,
          username: body.username,
          role: body.role,
          status: "active",
        };
        accounts = [...accounts, created];
        return json(created, 201);
      }
      const reset = path.match(/^\/api\/v1\/operators\/([^/]+)\/password$/);
      if (reset && method === "POST") {
        calls.reset.push({ id: reset[1], body });
        return overrides.reset?.() ?? new Response(null, { status: 204 });
      }
      const one = path.match(/^\/api\/v1\/operators\/([^/]+)$/);
      if (one && method === "PATCH") {
        calls.patch.push({ id: one[1], body });
        if (overrides.patch) return overrides.patch();
        accounts = accounts.map((item) =>
          item.id === one[1] ? { ...item, ...body } : item,
        );
        return json(accounts.find((item) => item.id === one[1]));
      }
      throw new Error(`unexpected request: ${method} ${path}`);
    }),
  );
  return calls;
}

function renderPage() {
  return render(
    <MemoryRouter>
      <AuthContext.Provider
        value={{
          token: "operator-token",
          username: "admin",
          role: "admin",
          setSession: vi.fn(),
        }}
      >
        <OperatorsPage />
      </AuthContext.Provider>
    </MemoryRouter>,
  );
}

const rowOf = (username: string) =>
  screen.getByRole("row", { name: new RegExp(`^${username}\\b`) });

async function loaded() {
  await screen.findByRole("row", { name: /^watcher\b/ });
}

async function openAndPress(username: string, opener: string, confirm: string) {
  await userEvent.click(within(rowOf(username)).getByRole("button", { name: opener }));
  await userEvent.click(within(rowOf(username)).getByRole("button", { name: confirm }));
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("OperatorsPage list", () => {
  it("shows every account with its role in Russian and its status", async () => {
    stubApi();
    renderPage();
    await loaded();

    expect(rowOf("watcher")).toHaveTextContent("наблюдатель");
    expect(rowOf("watcher")).toHaveTextContent("активен");
    expect(rowOf("second")).toHaveTextContent("администратор");
    expect(rowOf("gone")).toHaveTextContent("отключён");
  });

  it("marks the person's own row and offers nothing on it", async () => {
    stubApi();
    renderPage();
    await loaded();

    const own = rowOf("admin");

    expect(own).toHaveTextContent("это вы");
    expect(within(own).queryAllByRole("button")).toHaveLength(0);
  });

  it("offers the actions on every other account", async () => {
    stubApi();
    renderPage();
    await loaded();

    const other = within(rowOf("watcher"));
    expect(other.getByRole("button", { name: "Сменить роль" })).toBeInTheDocument();
    expect(other.getByRole("button", { name: "Отключить" })).toBeInTheDocument();
    expect(other.getByRole("button", { name: "Сбросить пароль" })).toBeInTheDocument();
    expect(
      within(rowOf("gone")).getByRole("button", { name: "Включить" }),
    ).toBeInTheDocument();
  });

  it("reports a failed load", async () => {
    stubApi({ list: () => json({ detail: "boom" }, 500) });
    renderPage();

    expect(await screen.findByText("Не удалось загрузить операторов")).toBeInTheDocument();
  });
});

describe("OperatorsPage create", () => {
  const fill = async (username: string, role: string, password: string) => {
    await userEvent.type(screen.getByLabelText("Имя пользователя"), username);
    await userEvent.selectOptions(screen.getByLabelText("Роль"), role);
    await userEvent.type(screen.getByLabelText("Пароль"), password);
    await userEvent.click(screen.getByRole("button", { name: "Создать" }));
  };

  it("posts the username, role and password, adds the row and clears the form", async () => {
    const calls = stubApi();
    renderPage();
    await loaded();

    await fill("colleague", "наблюдатель", PASSWORD);

    expect(await screen.findByText("Оператор создан")).toBeInTheDocument();
    expect(calls.create).toEqual([
      { username: "colleague", role: "viewer", password: PASSWORD },
    ]);
    expect(rowOf("colleague")).toHaveTextContent("наблюдатель");
    expect(screen.getByLabelText("Имя пользователя")).toHaveValue("");
    expect(screen.getByLabelText("Пароль")).toHaveValue("");
  });

  it("can create an administrator", async () => {
    const calls = stubApi();
    renderPage();
    await loaded();

    await fill("another", "администратор", PASSWORD);

    await screen.findByText("Оператор создан");
    expect(calls.create[0]).toMatchObject({ role: "admin" });
  });

  it("says a duplicate name exists", async () => {
    stubApi({ create: () => json({ detail: "exists" }, 409) });
    renderPage();
    await loaded();

    await fill("watcher", "наблюдатель", PASSWORD);

    expect(
      await screen.findByText("Оператор с таким именем уже существует"),
    ).toBeInTheDocument();
  });

  it("explains a refused name or password", async () => {
    stubApi({ create: () => json({ detail: "bad" }, 422) });
    renderPage();
    await loaded();

    await fill("colleague", "наблюдатель", "short");

    expect(await screen.findByText(/Проверьте имя и пароль/)).toBeInTheDocument();
  });

  it("says when the person lacks the rights", async () => {
    stubApi({ create: () => json({ detail: "no" }, 403) });
    renderPage();
    await loaded();

    await fill("colleague", "наблюдатель", PASSWORD);

    expect(await screen.findByText("Недостаточно прав")).toBeInTheDocument();
  });

  it("warns that the administrator knows the initial password", async () => {
    stubApi();
    renderPage();
    await loaded();

    expect(screen.getByText(/Администратор знает этот пароль/)).toBeInTheDocument();
  });
});

describe("OperatorsPage role", () => {
  it("changes a role only after «Применить», sending just the role", async () => {
    const calls = stubApi();
    renderPage();
    await loaded();
    await userEvent.click(
      within(rowOf("watcher")).getByRole("button", { name: "Сменить роль" }),
    );

    await userEvent.selectOptions(
      within(rowOf("watcher")).getByRole("combobox"),
      "администратор",
    );
    expect(calls.patch).toEqual([]);
    await userEvent.click(
      within(rowOf("watcher")).getByRole("button", { name: "Применить" }),
    );

    await waitFor(() => expect(rowOf("watcher")).toHaveTextContent("администратор"));
    expect(calls.patch).toEqual([{ id: "o-1", body: { role: "admin" } }]);
  });

  it("sends nothing when the change is cancelled", async () => {
    const calls = stubApi();
    renderPage();
    await loaded();
    await userEvent.click(
      within(rowOf("watcher")).getByRole("button", { name: "Сменить роль" }),
    );

    await userEvent.click(within(rowOf("watcher")).getByRole("button", { name: "Отмена" }));

    expect(calls.patch).toEqual([]);
    expect(rowOf("watcher")).toHaveTextContent("наблюдатель");
  });
});

describe("OperatorsPage disable and enable", () => {
  it("asks first, naming the account, and sends nothing until confirmed", async () => {
    const calls = stubApi();
    renderPage();
    await loaded();

    await userEvent.click(
      within(rowOf("watcher")).getByRole("button", { name: "Отключить" }),
    );

    expect(
      within(rowOf("watcher")).getByText(/Отключить оператора watcher\?/),
    ).toBeInTheDocument();
    expect(calls.patch).toEqual([]);
  });

  it("disables after confirmation and then offers to enable", async () => {
    const calls = stubApi();
    renderPage();
    await loaded();

    await openAndPress("watcher", "Отключить", "Да, отключить");

    await waitFor(() => expect(rowOf("watcher")).toHaveTextContent("отключён"));
    expect(calls.patch).toEqual([{ id: "o-1", body: { status: "disabled" } }]);
    expect(
      within(rowOf("watcher")).getByRole("button", { name: "Включить" }),
    ).toBeInTheDocument();
  });

  it("enables without a confirmation", async () => {
    const calls = stubApi();
    renderPage();
    await loaded();

    await userEvent.click(within(rowOf("gone")).getByRole("button", { name: "Включить" }));

    await waitFor(() => expect(rowOf("gone")).toHaveTextContent("активен"));
    expect(calls.patch).toEqual([{ id: "o-3", body: { status: "active" } }]);
  });

  it("sends nothing when the disabling is cancelled", async () => {
    const calls = stubApi();
    renderPage();
    await loaded();
    await userEvent.click(
      within(rowOf("watcher")).getByRole("button", { name: "Отключить" }),
    );

    await userEvent.click(within(rowOf("watcher")).getByRole("button", { name: "Отмена" }));

    expect(calls.patch).toEqual([]);
    expect(rowOf("watcher")).toHaveTextContent("активен");
  });
});

describe("OperatorsPage password reset", () => {
  const open = async (username: string) => {
    await userEvent.click(
      within(rowOf(username)).getByRole("button", { name: "Сбросить пароль" }),
    );
  };

  it("posts the new password once it is typed twice", async () => {
    const calls = stubApi();
    renderPage();
    await loaded();
    await open("watcher");

    await userEvent.type(within(rowOf("watcher")).getByLabelText("Новый пароль"), PASSWORD);
    await userEvent.type(
      within(rowOf("watcher")).getByLabelText("Повторите пароль"),
      PASSWORD,
    );
    await userEvent.click(
      within(rowOf("watcher")).getByRole("button", { name: "Применить" }),
    );

    expect(
      await screen.findByText("Пароль изменён. Сеансы оператора завершены."),
    ).toBeInTheDocument();
    expect(calls.reset).toEqual([{ id: "o-1", body: { new_password: PASSWORD } }]);
  });

  it("does not send a mismatched repeat", async () => {
    const calls = stubApi();
    renderPage();
    await loaded();
    await open("watcher");

    await userEvent.type(within(rowOf("watcher")).getByLabelText("Новый пароль"), PASSWORD);
    await userEvent.type(
      within(rowOf("watcher")).getByLabelText("Повторите пароль"),
      "different",
    );
    await userEvent.click(
      within(rowOf("watcher")).getByRole("button", { name: "Применить" }),
    );

    expect(await screen.findByText("Пароли не совпадают")).toBeInTheDocument();
    expect(calls.reset).toEqual([]);
  });

  it("sends nothing when cancelled", async () => {
    const calls = stubApi();
    renderPage();
    await loaded();
    await open("watcher");

    await userEvent.click(within(rowOf("watcher")).getByRole("button", { name: "Отмена" }));

    expect(calls.reset).toEqual([]);
    expect(
      within(rowOf("watcher")).queryByLabelText("Новый пароль"),
    ).not.toBeInTheDocument();
  });

  it("explains a refused password", async () => {
    stubApi({ reset: () => json({ detail: "bad" }, 422) });
    renderPage();
    await loaded();
    await open("watcher");
    await userEvent.type(within(rowOf("watcher")).getByLabelText("Новый пароль"), "short");
    await userEvent.type(
      within(rowOf("watcher")).getByLabelText("Повторите пароль"),
      "short",
    );

    await userEvent.click(
      within(rowOf("watcher")).getByRole("button", { name: "Применить" }),
    );

    expect(
      await screen.findByText(/Пароль не соответствует требованиям/),
    ).toBeInTheDocument();
  });
});

describe("OperatorsPage errors and focus", () => {
  it("says when an action is refused for lack of rights", async () => {
    stubApi({ patch: () => json({ detail: "no" }, 403) });
    renderPage();
    await loaded();

    await openAndPress("watcher", "Отключить", "Да, отключить");

    expect(await screen.findByText("Недостаточно прав")).toBeInTheDocument();
    expect(rowOf("watcher")).toHaveTextContent("активен");
  });

  it("says an account is gone when the server no longer knows it", async () => {
    stubApi({ patch: () => json({ detail: "Unknown operator" }, 404) });
    renderPage();
    await loaded();

    await openAndPress("watcher", "Отключить", "Да, отключить");

    expect(await screen.findByText("Оператор не найден")).toBeInTheDocument();
  });

  it("reports a failed action without changing the row", async () => {
    stubApi({ patch: () => json({ detail: "boom" }, 500) });
    renderPage();
    await loaded();

    await openAndPress("watcher", "Отключить", "Да, отключить");

    expect(await screen.findByText("Не удалось выполнить действие")).toBeInTheDocument();
    expect(rowOf("watcher")).toHaveTextContent("активен");
  });

  it("keeps a single inline panel open at a time", async () => {
    stubApi();
    renderPage();
    await loaded();
    await userEvent.click(
      within(rowOf("watcher")).getByRole("button", { name: "Отключить" }),
    );
    expect(
      within(rowOf("watcher")).getByText(/Отключить оператора watcher\?/),
    ).toBeInTheDocument();

    await userEvent.click(
      within(rowOf("second")).getByRole("button", { name: "Сбросить пароль" }),
    );

    expect(screen.queryByText(/Отключить оператора watcher\?/)).not.toBeInTheDocument();
    expect(within(rowOf("second")).getByLabelText("Новый пароль")).toBeInTheDocument();
  });
});
