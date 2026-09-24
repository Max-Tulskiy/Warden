import { useEffect, useState, type FormEvent } from "react";

import {
  ApiError,
  changePassword,
  getPolicy,
  listAgents,
  logoutAll,
  setAgentStatus,
} from "../api/client";
import type { Agent, Policy } from "../api/types";
import { AppShell } from "../components/AppShell";
import { PolicyCard } from "../components/PolicyCard";
import { StatusPill } from "../components/StatusPill";
import { validateNewPassword } from "../lib/passwordValidation";
import { stationStatus } from "../lib/stationStatus";
import { useAuth } from "../state/authContext";

function passwordErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 400) return "Неверный текущий пароль";
    if (error.status === 429) return "Слишком много попыток. Повторите позже";
    if (error.status === 422)
      return "Сервер отклонил новый пароль: он не соответствует требованиям";
  }
  return "Не удалось сменить пароль";
}

export function SettingsPage() {
  const { token, username, role, setSession } = useAuth();
  const [policy, setPolicy] = useState<Policy | null>(null);
  const [policyError, setPolicyError] = useState<string | null>(null);
  const [stations, setStations] = useState<Agent[] | null>(null);
  const [stationsError, setStationsError] = useState<string | null>(null);

  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [repeatPassword, setRepeatPassword] = useState("");
  const [changing, setChanging] = useState(false);
  const [passwordError, setPasswordError] = useState<string | null>(null);
  const [passwordMessage, setPasswordMessage] = useState<string | null>(null);

  const [confirmingSessions, setConfirmingSessions] = useState(false);
  const [endingSessions, setEndingSessions] = useState(false);
  const [sessionsError, setSessionsError] = useState<string | null>(null);

  const [confirmingId, setConfirmingId] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [stationActionError, setStationActionError] = useState<string | null>(null);

  useEffect(() => {
    if (!token) return;
    let cancelled = false;

    getPolicy(token)
      .then((loaded) => {
        if (!cancelled) setPolicy(loaded);
      })
      .catch(() => {
        if (!cancelled) setPolicyError("Не удалось загрузить политику сервера");
      });

    return () => {
      cancelled = true;
    };
  }, [token]);

  // Enabling and disabling stations is an administrator's job, so only an
  // administrator loads the list; an observer never sees this card at all.
  useEffect(() => {
    if (!token || role !== "admin") return;
    let cancelled = false;

    listAgents(token)
      .then((loaded) => {
        if (!cancelled) setStations(loaded);
      })
      .catch(() => {
        if (!cancelled) setStationsError("Не удалось загрузить список станций");
      });

    return () => {
      cancelled = true;
    };
  }, [token, role]);

  const handlePasswordSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setPasswordError(null);
    setPasswordMessage(null);
    if (!token) return;

    // Without the policy the length check is skipped here; the server still enforces it.
    const problem = validateNewPassword(
      currentPassword,
      newPassword,
      repeatPassword,
      policy?.min_password_length ?? 0,
    );
    if (problem) {
      setPasswordError(problem);
      return;
    }

    setChanging(true);
    try {
      // The server ended every session issued so far and handed back a token
      // for the new version: storing it is what keeps this one signed in.
      const renewed = await changePassword(token, currentPassword, newPassword);
      setSession({ token: renewed, username: username ?? "" });
      setCurrentPassword("");
      setNewPassword("");
      setRepeatPassword("");
      setPasswordMessage("Пароль изменён. Остальные сеансы завершены.");
    } catch (error) {
      setPasswordError(passwordErrorMessage(error));
    } finally {
      setChanging(false);
    }
  };

  const handleEndSessions = async () => {
    if (!token) return;
    setEndingSessions(true);
    setSessionsError(null);
    try {
      await logoutAll(token);
      // This session ended too; clearing it sends the operator to sign-in.
      setSession(null);
    } catch {
      setSessionsError("Не удалось завершить сеансы");
      setEndingSessions(false);
    }
  };

  const applyStatus = async (station: Agent, status: Agent["status"]) => {
    if (!token) return;
    setBusyId(station.id);
    setStationActionError(null);
    try {
      const updated = await setAgentStatus(token, station.id, status);
      setStations((current) =>
        current
          ? current.map((item) => (item.id === updated.id ? updated : item))
          : current,
      );
      setConfirmingId(null);
    } catch {
      setStationActionError("Не удалось изменить статус станции");
    } finally {
      setBusyId(null);
    }
  };

  return (
    <AppShell narrow>
      <h1 style={{ margin: "0 0 24px 0", fontSize: 20, fontWeight: 700 }}>Настройки</h1>

      <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
        <section className="card">
          <h2 style={{ margin: "0 0 14px 0", fontSize: 15, fontWeight: 600 }}>
            Смена пароля
          </h2>
          <form
            onSubmit={handlePasswordSubmit}
            style={{ display: "flex", flexDirection: "column", gap: 14, maxWidth: 360 }}
          >
            <label>
              Текущий пароль
              <input
                type="password"
                autoComplete="current-password"
                value={currentPassword}
                onChange={(e) => setCurrentPassword(e.target.value)}
              />
            </label>
            <label>
              Новый пароль
              <input
                type="password"
                autoComplete="new-password"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
              />
            </label>
            <label>
              Повторите новый пароль
              <input
                type="password"
                autoComplete="new-password"
                value={repeatPassword}
                onChange={(e) => setRepeatPassword(e.target.value)}
              />
            </label>
            <div>
              <button className="btn-primary" type="submit" disabled={changing}>
                {changing ? "Сохранение..." : "Сменить пароль"}
              </button>
            </div>
          </form>
          {passwordError && (
            <p className="error" style={{ marginBottom: 0 }}>
              {passwordError}
            </p>
          )}
          {passwordMessage && (
            <p className="muted" style={{ marginBottom: 0 }}>
              {passwordMessage}
            </p>
          )}
          {policy && !passwordError && !passwordMessage && (
            <p className="field-hint" style={{ marginBottom: 0 }}>
              Не короче {policy.min_password_length} символов. Смена пароля завершает все
              остальные сеансы, а этот остаётся.
            </p>
          )}
        </section>

        <section className="card">
          <h2 style={{ margin: "0 0 14px 0", fontSize: 15, fontWeight: 600 }}>Сеансы</h2>
          <p className="text-secondary" style={{ marginTop: 0 }}>
            Завершение всех сеансов выведет вас из панели на всех устройствах, включая это,
            и потребует войти заново.
          </p>
          {sessionsError && <p className="error">{sessionsError}</p>}
          {confirmingSessions ? (
            <div className="confirm-inline">
              <span>Завершить все сеансы, включая этот?</span>
              <button
                className="btn-danger"
                type="button"
                disabled={endingSessions}
                onClick={handleEndSessions}
              >
                Да, завершить
              </button>
              <button
                className="btn-secondary"
                type="button"
                disabled={endingSessions}
                onClick={() => setConfirmingSessions(false)}
              >
                Отмена
              </button>
            </div>
          ) : (
            <button
              className="btn-secondary"
              type="button"
              onClick={() => setConfirmingSessions(true)}
            >
              Завершить все сеансы
            </button>
          )}
        </section>

        <PolicyCard policy={policy} error={policyError} onChange={setPolicy} />

        {role === "admin" && (
          <section className="card" style={{ padding: "20px 0 4px 0" }}>
            <h2
              style={{
                margin: "0 0 14px 0",
                padding: "0 22px",
                fontSize: 15,
                fontWeight: 600,
              }}
            >
              Станции
            </h2>
            {stationsError && (
              <p className="error" style={{ padding: "0 22px" }}>
                {stationsError}
              </p>
            )}
            {stationActionError && (
              <p className="error" style={{ padding: "0 22px" }}>
                {stationActionError}
              </p>
            )}
            {!stations && !stationsError && (
              <p className="text-secondary" style={{ padding: "0 22px" }}>
                Загрузка...
              </p>
            )}
            {stations && stations.length === 0 && (
              <p className="muted" style={{ padding: "0 22px" }}>
                Нет зарегистрированных станций.
              </p>
            )}
            {stations && stations.length > 0 && (
              <table>
                <thead>
                  <tr>
                    <th style={{ width: "28%" }}>Станция</th>
                    <th style={{ width: "14%" }}>ОС</th>
                    <th style={{ width: "18%" }}>Статус</th>
                    <th>Действие</th>
                  </tr>
                </thead>
                <tbody>
                  {stations.map((station) => (
                    <tr key={station.id}>
                      <td className="mono" style={{ fontWeight: 500 }}>
                        {station.hostname}
                      </td>
                      <td className="text-secondary">{station.os}</td>
                      <td>
                        <StatusPill status={stationStatus(station)} />
                      </td>
                      <td>
                        {station.status === "disabled" ? (
                          <button
                            className="btn-secondary"
                            type="button"
                            disabled={busyId === station.id}
                            onClick={() => applyStatus(station, "active")}
                          >
                            Включить
                          </button>
                        ) : confirmingId === station.id ? (
                          <div className="confirm-inline">
                            <span>
                              Отключить станцию {station.hostname}? Её агент перестанет
                              проходить проверку подлинности.
                            </span>
                            <button
                              className="btn-danger"
                              type="button"
                              disabled={busyId === station.id}
                              onClick={() => applyStatus(station, "disabled")}
                            >
                              Да, отключить
                            </button>
                            <button
                              className="btn-secondary"
                              type="button"
                              onClick={() => setConfirmingId(null)}
                            >
                              Отмена
                            </button>
                          </div>
                        ) : (
                          <button
                            className="btn-secondary"
                            type="button"
                            onClick={() => setConfirmingId(station.id)}
                          >
                            Отключить
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </section>
        )}
      </div>
    </AppShell>
  );
}
