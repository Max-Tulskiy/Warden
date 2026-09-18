import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";

import { ApiError, login } from "../api/client";
import { ShieldIcon } from "../components/icons";
import { useAuth } from "../state/authContext";

export function LoginPage() {
  const { setSession } = useAuth();
  const navigate = useNavigate();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const token = await login(username, password);
      setSession({ token, username });
      navigate("/agents");
    } catch (err) {
      setError(
        err instanceof ApiError
          ? "Неверное имя пользователя или пароль"
          : "Не удалось подключиться к серверу",
      );
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <main className="login-screen">
      <form className="login-card" onSubmit={handleSubmit}>
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <ShieldIcon size={26} color="var(--accent)" />
            <span style={{ fontSize: 19, fontWeight: 700, letterSpacing: "0.2px" }}>
              Warden
            </span>
          </div>
          <div className="text-secondary" style={{ fontSize: 13, lineHeight: 1.5 }}>
            Комплекс мониторинга рабочих станций
          </div>
        </div>

        <div className="login-divider" />

        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          <label>
            Имя пользователя
            <input
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              autoFocus
              required
            />
          </label>
          <label>
            Пароль
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          </label>
        </div>

        {error && <p className="error">{error}</p>}

        <button
          className="btn-primary"
          type="submit"
          disabled={submitting}
          style={{ width: "100%" }}
        >
          {submitting ? "Вход..." : "Войти"}
        </button>

        <div className="text-tertiary" style={{ fontSize: 12, textAlign: "center" }}>
          Доступ только для администраторов информационной безопасности
        </div>
      </form>
    </main>
  );
}
