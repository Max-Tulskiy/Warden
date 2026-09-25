import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import {
  ApiError,
  createEnrollmentToken,
  getTlsAuthority,
  listAgents,
} from "../api/client";
import type { Agent, EnrollmentToken, TlsAuthority } from "../api/types";
import { AppShell } from "../components/AppShell";
import { CopyIcon, KeyIcon } from "../components/icons";
import { StatusPill } from "../components/StatusPill";
import { formatFingerprint } from "../lib/fingerprint";
import { stationStatus } from "../lib/stationStatus";
import { useAuth } from "../state/authContext";

export function AgentsPage() {
  const { token, role } = useAuth();
  const [agents, setAgents] = useState<Agent[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [enrollmentToken, setEnrollmentToken] = useState<EnrollmentToken | null>(null);
  const [tokenError, setTokenError] = useState<string | null>(null);
  const [tokenMessage, setTokenMessage] = useState<string | null>(null);
  const [issuingToken, setIssuingToken] = useState(false);
  // What the server publishes about its own certificate authority: the
  // authority itself, `"none"` when it has none, `null` while unknown or failed.
  const [authority, setAuthority] = useState<TlsAuthority | "none" | null>(null);

  useEffect(() => {
    if (!token) return;
    listAgents(token)
      .then(setAgents)
      .catch(() => setError("Не удалось загрузить список станций"));
  }, [token]);

  useEffect(() => {
    if (role !== "admin") return;
    getTlsAuthority()
      .then(setAuthority)
      .catch((error: unknown) => {
        setAuthority(error instanceof ApiError && error.status === 404 ? "none" : null);
      });
  }, [role]);

  const onlineCount = useMemo(
    () => agents?.filter((agent) => stationStatus(agent) === "online").length ?? 0,
    [agents],
  );

  const handleCreateEnrollmentToken = async () => {
    if (!token) return;
    setIssuingToken(true);
    setTokenError(null);
    setTokenMessage(null);
    try {
      setEnrollmentToken(await createEnrollmentToken(token));
    } catch {
      setTokenError("Не удалось выпустить регистрационный токен");
    } finally {
      setIssuingToken(false);
    }
  };

  const handleCopyEnrollmentToken = async () => {
    if (!enrollmentToken) return;
    try {
      await navigator.clipboard.writeText(enrollmentToken.token);
      setTokenMessage("Токен скопирован");
    } catch {
      setTokenError("Не удалось скопировать токен");
    }
  };

  return (
    <AppShell>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          flexWrap: "wrap",
          gap: 12,
          marginBottom: 20,
        }}
      >
        <div style={{ display: "flex", alignItems: "baseline", flexWrap: "wrap", gap: 12 }}>
          <h1 style={{ margin: 0, fontSize: 20, fontWeight: 700 }}>Станции</h1>
          {agents && (
            <span className="text-tertiary" style={{ fontSize: 13 }}>
              {agents.length} всего · {onlineCount} в сети
            </span>
          )}
        </div>
        {role === "admin" && (
          <button
            className="btn-primary"
            type="button"
            onClick={handleCreateEnrollmentToken}
            disabled={issuingToken}
          >
            <KeyIcon />
            {issuingToken ? "Выпуск..." : "Выпустить токен"}
          </button>
        )}
      </div>

      {role === "admin" && authority === "none" && (
        <p className="muted" style={{ marginTop: 0 }}>
          Сервер использует сертификат, который система уже проверяет: сверять отпечаток не
          нужно.
        </p>
      )}
      {role === "admin" && authority !== null && authority !== "none" && (
        <div className="notice" style={{ marginBottom: 18 }}>
          <div>
            <div className="notice-title">Отпечаток сертификата сервера (SHA-256)</div>
            <div className="mono token-value">{formatFingerprint(authority.sha256)}</div>
            <div className="text-tertiary" style={{ fontSize: 12, marginTop: 6 }}>
              Сверьте его с отпечатком в окне настройки агента, прежде чем доверять серверу.
            </div>
          </div>
        </div>
      )}

      {enrollmentToken && (
        <div className="notice" style={{ marginBottom: 18 }}>
          <div>
            <div className="notice-title">Токен регистрации</div>
            <div className="mono token-value">{enrollmentToken.token}</div>
            <div className="text-tertiary" style={{ fontSize: 12, marginTop: 6 }}>
              Действует до {new Date(enrollmentToken.expires_at).toLocaleString("ru-RU")}
            </div>
          </div>
          <button
            className="btn-secondary"
            type="button"
            onClick={handleCopyEnrollmentToken}
            aria-label="Скопировать токен"
            title="Скопировать токен"
          >
            <CopyIcon />
            Скопировать
          </button>
        </div>
      )}
      {tokenMessage && (
        <p className="muted" style={{ marginTop: -8 }}>
          {tokenMessage}
        </p>
      )}
      {tokenError && (
        <p className="error" style={{ marginTop: -8 }}>
          {tokenError}
        </p>
      )}

      {error && <p className="error">{error}</p>}
      {!agents && !error && <p className="text-secondary">Загрузка...</p>}
      {agents && agents.length === 0 && (
        <p className="muted">Нет зарегистрированных агентов.</p>
      )}

      {agents && agents.length > 0 && (
        <div className="card" style={{ padding: 0, overflow: "hidden" }}>
          <table>
            <thead>
              <tr>
                <th style={{ width: "32%" }}>Станция</th>
                <th style={{ width: "16%" }}>ОС</th>
                <th style={{ width: "20%" }}>Статус</th>
                <th>Последняя активность</th>
              </tr>
            </thead>
            <tbody>
              {agents.map((agent) => (
                <tr key={agent.id}>
                  <td>
                    <Link
                      to={`/agents/${agent.id}`}
                      className="mono"
                      style={{ fontWeight: 500 }}
                    >
                      {agent.hostname}
                    </Link>
                  </td>
                  <td className="text-secondary">{agent.os}</td>
                  <td>
                    <StatusPill status={stationStatus(agent)} />
                  </td>
                  <td className="mono text-secondary">
                    {agent.last_seen_at
                      ? new Date(agent.last_seen_at).toLocaleString("ru-RU")
                      : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </AppShell>
  );
}
