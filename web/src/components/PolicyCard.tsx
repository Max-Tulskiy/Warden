import { useState, type FormEvent } from "react";

import { ApiError, resetPolicy, savePolicy } from "../api/client";
import type { EditablePolicy, Policy } from "../api/types";
import {
  formatCount,
  POLICY_FIELDS,
  validatePolicyForm,
  type PolicyField,
} from "../lib/policyFormat";
import { useAuth } from "../state/authContext";

const SAVED_MESSAGE =
  "Политика сохранена. Новый предел окна действует для следующих запросов, срок сеанса — для новых входов, срок токена — для новых токенов; уже выданные сеансы, токены и запросы сохраняют свой срок.";
const RESET_MESSAGE = "Значения возвращены к конфигурации сервера.";

type Form = Record<PolicyField, string>;

function toForm(policy: EditablePolicy): Form {
  return {
    max_request_window_hours: String(policy.max_request_window_hours),
    enrollment_token_ttl_hours: String(policy.enrollment_token_ttl_hours),
    session_lifetime_minutes: String(policy.session_lifetime_minutes),
  };
}

function writeErrorMessage(error: unknown, resetting: boolean): string {
  if (error instanceof ApiError) {
    if (error.status === 403) return "Недостаточно прав";
    if (error.status === 422)
      return "Сервер отклонил значения. Проверьте допустимые диапазоны";
  }
  return resetting ? "Не удалось сбросить политику" : "Не удалось сохранить политику";
}

/** The limits that stay in the server's configuration: always read-only. */
function fixedRows(policy: Policy): { label: string; value: string }[] {
  return [
    { label: "Минимальная длина пароля", value: `${policy.min_password_length} симв.` },
    {
      label: "Максимум событий в одном отчёте агента",
      value: formatCount(policy.max_report_events),
    },
    {
      label: "Максимум записей в снимке инвентаризации",
      value: formatCount(policy.max_inventory_entries),
    },
    {
      label: "Максимум записей на страницу отчёта",
      value: formatCount(policy.max_page_size),
    },
  ];
}

function editableRows(policy: Policy): { label: string; value: string }[] {
  return POLICY_FIELDS.map((field) => ({
    label: field.label,
    value: field.format(policy[field.key]),
  }));
}

interface EditorProps {
  policy: Policy;
  onDone: (next: Policy, message: string) => void;
}

/**
 * The form for an administrator. It starts from the policy it is given, and the
 * card gives it a new key whenever a save or a reset changes that policy, so it
 * is rebuilt from what the server now says rather than kept in step by hand.
 */
function PolicyEditor({ policy, onDone }: EditorProps) {
  const { token } = useAuth();
  const [form, setForm] = useState<Form>(() => toForm(policy));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confirmingReset, setConfirmingReset] = useState(false);

  const handleSave = async (event: FormEvent) => {
    event.preventDefault();
    if (!token) return;
    setError(null);
    const checked = validatePolicyForm(form, policy.bounds);
    if ("error" in checked) {
      setError(checked.error);
      return;
    }
    setBusy(true);
    try {
      onDone(await savePolicy(token, checked.values), SAVED_MESSAGE);
    } catch (failure) {
      setError(writeErrorMessage(failure, false));
    } finally {
      setBusy(false);
    }
  };

  const handleReset = async () => {
    if (!token) return;
    setError(null);
    setBusy(true);
    try {
      onDone(await resetPolicy(token), RESET_MESSAGE);
    } catch (failure) {
      setError(writeErrorMessage(failure, true));
      setConfirmingReset(false);
    } finally {
      setBusy(false);
    }
  };

  const defaults = policy.defaults;
  const defaultsText = `окно ${POLICY_FIELDS[0].format(defaults.max_request_window_hours)}, токен ${POLICY_FIELDS[1].format(defaults.enrollment_token_ttl_hours)}, сеанс ${POLICY_FIELDS[2].format(defaults.session_lifetime_minutes)}`;

  return (
    // noValidate: the browser's own bubble would block a value like 2.5 before the
    // panel could name the range, so the panel does the checking (and the server
    // still does its own).
    <form onSubmit={handleSave} noValidate style={{ marginBottom: 14 }}>
      <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
        {POLICY_FIELDS.map((field) => (
          <div key={field.key} className="policy-edit">
            <label htmlFor={`policy-${field.key}`}>{field.label}</label>
            <div className="policy-edit-control">
              <input
                id={`policy-${field.key}`}
                type="number"
                inputMode="numeric"
                min={policy.bounds[field.key].min}
                max={policy.bounds[field.key].max}
                step={1}
                value={form[field.key]}
                onChange={(e) => setForm({ ...form, [field.key]: e.target.value })}
              />
              <span className="text-secondary">{field.unit}</span>
            </div>
            <span className="field-hint" style={{ margin: 0 }}>
              {`${field.range(policy.bounds[field.key])} · по умолчанию: ${field.format(defaults[field.key])}`}
            </span>
          </div>
        ))}
      </div>

      <div className="filter-actions" style={{ marginTop: 14, gap: 10 }}>
        <button className="btn-primary" type="submit" disabled={busy}>
          Сохранить
        </button>
        {policy.overridden && !confirmingReset && (
          <button
            className="btn-secondary"
            type="button"
            disabled={busy}
            onClick={() => setConfirmingReset(true)}
          >
            Сбросить к значениям сервера
          </button>
        )}
      </div>

      {confirmingReset && (
        <div className="confirm-inline" style={{ marginTop: 12 }}>
          <span>
            Вернуть значения из конфигурации сервера ({defaultsText})? Сохранённая политика
            будет удалена.
          </span>
          <button
            className="btn-danger"
            type="button"
            disabled={busy}
            onClick={handleReset}
          >
            Да, сбросить
          </button>
          <button
            className="btn-secondary"
            type="button"
            disabled={busy}
            onClick={() => setConfirmingReset(false)}
          >
            Отмена
          </button>
        </div>
      )}
      {error && (
        <p className="error" style={{ marginBottom: 0 }}>
          {error}
        </p>
      )}
    </form>
  );
}

interface CardProps {
  policy: Policy | null;
  error: string | null;
  /** Called with the policy in force after an administrator's save or reset. */
  onChange: (policy: Policy) => void;
}

export function PolicyCard({ policy, error, onChange }: CardProps) {
  const { role } = useAuth();
  const [message, setMessage] = useState<string | null>(null);

  const done = (next: Policy, text: string) => {
    setMessage(text);
    onChange(next);
  };

  const rows = policy
    ? role === "admin"
      ? fixedRows(policy)
      : [...editableRows(policy), ...fixedRows(policy)]
    : [];
  // A new key rebuilds the editor from the policy the server now reports.
  const editorKey = policy ? `${policy.overridden}:${JSON.stringify(toForm(policy))}` : "";

  return (
    <section className="card">
      <h2 style={{ margin: "0 0 14px 0", fontSize: 15, fontWeight: 600 }}>
        Политика сервера
      </h2>
      {error && <p className="error">{error}</p>}
      {!policy && !error && <p className="text-secondary">Загрузка...</p>}
      {policy && role === "admin" && (
        <>
          <p className="muted" style={{ margin: "0 0 12px 0" }}>
            {policy.overridden
              ? "Сохранена политика администратора"
              : "Действуют значения из конфигурации сервера"}
          </p>
          <PolicyEditor key={editorKey} policy={policy} onDone={done} />
          {message && (
            <p role="status" className="muted" style={{ margin: "0 0 14px 0" }}>
              {message}
            </p>
          )}
        </>
      )}
      {policy && (
        <dl className="policy-list">
          {rows.map((row) => (
            <div key={row.label} className="policy-row">
              <dt>{row.label}</dt>
              <dd className="mono">{row.value}</dd>
            </div>
          ))}
        </dl>
      )}
      {policy && role === "viewer" && (
        <p className="field-hint" style={{ margin: "0 0 8px 0" }}>
          Изменять политику могут только администраторы.
        </p>
      )}
      <p className="field-hint" style={{ marginBottom: 0 }}>
        Пределы загрузки, размер страницы и минимальная длина пароля задаются конфигурацией
        сервера и из панели не меняются.
      </p>
    </section>
  );
}
