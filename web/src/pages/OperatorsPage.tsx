import { useEffect, useState, type FormEvent } from "react";

import {
  ApiError,
  createOperator,
  listOperators,
  resetOperatorPassword,
  updateOperator,
} from "../api/client";
import type { Operator, Role } from "../api/types";
import { AppShell } from "../components/AppShell";
import { useAuth } from "../state/authContext";

const ROLE_LABELS: Record<Role, string> = {
  admin: "администратор",
  viewer: "наблюдатель",
};

const ROLES: Role[] = ["viewer", "admin"];

type Panel = { id: string; kind: "role" | "disable" | "reset" } | null;

function sortAccounts(accounts: Operator[]): Operator[] {
  return [...accounts].sort((a, b) => a.username.localeCompare(b.username));
}

function AccountStatus({ status }: { status: Operator["status"] }) {
  const active = status === "active";
  const color = active ? "var(--success)" : "var(--warning)";
  return (
    <span
      className="pill"
      style={{ background: active ? "var(--success-bg)" : "var(--warning-bg)", color }}
    >
      <span className="pill-dot" style={{ background: color }} />
      {active ? "активен" : "отключён"}
    </span>
  );
}

function createErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 403) return "Недостаточно прав";
    if (error.status === 409) return "Оператор с таким именем уже существует";
    if (error.status === 422) {
      return (
        "Проверьте имя и пароль: имя — латинские буквы, цифры и . _ @ - (до 64 символов), " +
        "пароль — не короче минимальной длины из настроек"
      );
    }
  }
  return "Не удалось создать оператора";
}

function actionErrorMessage(error: unknown, resetting: boolean): string {
  if (error instanceof ApiError) {
    if (error.status === 403) return "Недостаточно прав";
    if (error.status === 404) return "Оператор не найден";
    if (error.status === 409) return "Нельзя изменить собственную учётную запись";
    if (error.status === 422 && resetting) {
      return "Пароль не соответствует требованиям: он короче минимальной длины из настроек или слишком длинный";
    }
  }
  return "Не удалось выполнить действие";
}

export function OperatorsPage() {
  const { token, username: me } = useAuth();
  const [accounts, setAccounts] = useState<Operator[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [newUsername, setNewUsername] = useState("");
  const [newRole, setNewRole] = useState<Role>("viewer");
  const [newPassword, setNewPassword] = useState("");
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  const [panel, setPanel] = useState<Panel>(null);
  const [pendingRole, setPendingRole] = useState<Role>("viewer");
  const [resetNew, setResetNew] = useState("");
  const [resetRepeat, setResetRepeat] = useState("");
  const [busyId, setBusyId] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    listOperators(token)
      .then((loaded) => {
        if (!cancelled) setAccounts(sortAccounts(loaded));
      })
      .catch(() => {
        if (!cancelled) setLoadError("Не удалось загрузить операторов");
      });
    return () => {
      cancelled = true;
    };
  }, [token]);

  const openPanel = (next: Panel, account?: Operator) => {
    setPanel(next);
    setActionError(null);
    setMessage(null);
    setResetNew("");
    setResetRepeat("");
    if (account) setPendingRole(account.role);
  };

  const replace = (updated: Operator) =>
    setAccounts((current) =>
      current ? current.map((item) => (item.id === updated.id ? updated : item)) : current,
    );

  const handleCreate = async (event: FormEvent) => {
    event.preventDefault();
    if (!token) return;
    setCreating(true);
    setCreateError(null);
    setMessage(null);
    try {
      const created = await createOperator(token, {
        username: newUsername.trim(),
        role: newRole,
        password: newPassword,
      });
      setAccounts((current) => sortAccounts([...(current ?? []), created]));
      setNewUsername("");
      setNewPassword("");
      setNewRole("viewer");
      setMessage("Оператор создан");
    } catch (error) {
      setCreateError(createErrorMessage(error));
    } finally {
      setCreating(false);
    }
  };

  const change = async (
    account: Operator,
    changes: { role?: Role; status?: Operator["status"] },
  ) => {
    if (!token) return;
    setBusyId(account.id);
    setActionError(null);
    try {
      replace(await updateOperator(token, account.id, changes));
      setPanel(null);
    } catch (error) {
      setActionError(actionErrorMessage(error, false));
    } finally {
      setBusyId(null);
    }
  };

  const handleReset = async (account: Operator) => {
    if (!token || !resetNew) return;
    if (resetNew !== resetRepeat) {
      setActionError("Пароли не совпадают");
      return;
    }
    setBusyId(account.id);
    setActionError(null);
    try {
      await resetOperatorPassword(token, account.id, resetNew);
      setPanel(null);
      setMessage("Пароль изменён. Сеансы оператора завершены.");
    } catch (error) {
      setActionError(actionErrorMessage(error, true));
    } finally {
      setBusyId(null);
    }
  };

  const actionsFor = (account: Operator) => {
    const busy = busyId === account.id;
    if (panel?.id === account.id && panel.kind === "role") {
      return (
        <div className="confirm-inline">
          <select
            aria-label="Новая роль"
            value={pendingRole}
            onChange={(e) => setPendingRole(e.target.value as Role)}
          >
            {ROLES.map((role) => (
              <option key={role} value={role}>
                {ROLE_LABELS[role]}
              </option>
            ))}
          </select>
          <button
            className="btn-primary"
            type="button"
            disabled={busy}
            onClick={() => change(account, { role: pendingRole })}
          >
            Применить
          </button>
          <button className="btn-secondary" type="button" onClick={() => setPanel(null)}>
            Отмена
          </button>
        </div>
      );
    }
    if (panel?.id === account.id && panel.kind === "disable") {
      return (
        <div className="confirm-inline">
          <span>Отключить оператора {account.username}? Его сеансы будут завершены.</span>
          <button
            className="btn-danger"
            type="button"
            disabled={busy}
            onClick={() => change(account, { status: "disabled" })}
          >
            Да, отключить
          </button>
          <button className="btn-secondary" type="button" onClick={() => setPanel(null)}>
            Отмена
          </button>
        </div>
      );
    }
    if (panel?.id === account.id && panel.kind === "reset") {
      return (
        <div className="confirm-inline">
          <label>
            Новый пароль
            <input
              type="password"
              autoComplete="new-password"
              value={resetNew}
              onChange={(e) => setResetNew(e.target.value)}
            />
          </label>
          <label>
            Повторите пароль
            <input
              type="password"
              autoComplete="new-password"
              value={resetRepeat}
              onChange={(e) => setResetRepeat(e.target.value)}
            />
          </label>
          <button
            className="btn-primary"
            type="button"
            disabled={busy}
            onClick={() => handleReset(account)}
          >
            Применить
          </button>
          <button className="btn-secondary" type="button" onClick={() => setPanel(null)}>
            Отмена
          </button>
        </div>
      );
    }
    return (
      <div className="confirm-inline">
        <button
          className="btn-secondary"
          type="button"
          onClick={() => openPanel({ id: account.id, kind: "role" }, account)}
        >
          Сменить роль
        </button>
        {account.status === "disabled" ? (
          <button
            className="btn-secondary"
            type="button"
            disabled={busy}
            onClick={() => change(account, { status: "active" })}
          >
            Включить
          </button>
        ) : (
          <button
            className="btn-secondary"
            type="button"
            onClick={() => openPanel({ id: account.id, kind: "disable" })}
          >
            Отключить
          </button>
        )}
        <button
          className="btn-secondary"
          type="button"
          onClick={() => openPanel({ id: account.id, kind: "reset" })}
        >
          Сбросить пароль
        </button>
      </div>
    );
  };

  return (
    <AppShell>
      <h1 style={{ margin: "0 0 20px 0", fontSize: 20, fontWeight: 700 }}>Операторы</h1>

      <form className="card report-filters" onSubmit={handleCreate}>
        <div className="filter-row">
          <label style={{ flex: 1 }}>
            Имя пользователя
            <input
              value={newUsername}
              maxLength={64}
              autoComplete="off"
              onChange={(e) => setNewUsername(e.target.value)}
              required
            />
          </label>
          <label style={{ minWidth: 200 }}>
            Роль
            <select value={newRole} onChange={(e) => setNewRole(e.target.value as Role)}>
              {ROLES.map((role) => (
                <option key={role} value={role}>
                  {ROLE_LABELS[role]}
                </option>
              ))}
            </select>
          </label>
          <label style={{ flex: 1 }}>
            Пароль
            <input
              type="password"
              autoComplete="new-password"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              required
            />
          </label>
        </div>
        <div className="filter-actions">
          <button className="btn-primary" type="submit" disabled={creating}>
            Создать
          </button>
        </div>
        {createError && (
          <p className="error" style={{ margin: 0 }}>
            {createError}
          </p>
        )}
        <p className="field-hint" style={{ margin: 0 }}>
          Администратор знает этот пароль, пока человек не сменит его после первого входа.
        </p>
      </form>

      {message && (
        <p role="status" className="muted" style={{ margin: "16px 0 0 0" }}>
          {message}
        </p>
      )}

      <section className="card" style={{ padding: "20px 0 4px 0", marginTop: 20 }}>
        <h2
          style={{ margin: "0 0 14px 0", padding: "0 22px", fontSize: 15, fontWeight: 600 }}
        >
          Учётные записи
        </h2>
        {loadError && (
          <p className="error" style={{ padding: "0 22px" }}>
            {loadError}
          </p>
        )}
        {actionError && (
          <p className="error" style={{ padding: "0 22px" }}>
            {actionError}
          </p>
        )}
        {!accounts && !loadError && (
          <p className="text-secondary" style={{ padding: "0 22px" }}>
            Загрузка...
          </p>
        )}
        {accounts && (
          <table>
            <thead>
              <tr>
                <th style={{ width: "20%" }}>Имя</th>
                <th style={{ width: "16%" }}>Роль</th>
                <th style={{ width: "14%" }}>Статус</th>
                <th>Действия</th>
              </tr>
            </thead>
            <tbody>
              {accounts.map((account) => (
                <tr key={account.id}>
                  <td
                    className="mono"
                    style={{ fontWeight: 500, overflowWrap: "anywhere" }}
                  >
                    {account.username}
                  </td>
                  <td>{ROLE_LABELS[account.role]}</td>
                  <td>
                    <AccountStatus status={account.status} />
                  </td>
                  <td>
                    {account.username === me ? (
                      <span className="text-tertiary">это вы</span>
                    ) : (
                      actionsFor(account)
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </AppShell>
  );
}
