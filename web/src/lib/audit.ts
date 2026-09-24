import type { Agent } from "../api/types";

/**
 * Russian names of the action codes the server writes to the audit log.
 * A later server version may write a code not listed here; `actionLabel`
 * shows such a code as it is, so an entry is never hidden by a missing name.
 */
const ACTION_LABELS: Record<string, string> = {
  "agent.enroll": "Регистрация станции",
  "agent.enroll_rejected": "Отклонена регистрация станции",
  "agent.inventory_change": "Обнаружено изменение конфигурации",
  "agent.inventory_snapshot": "Получен снимок инвентаризации",
  "agent.report": "Получен отчёт за окно",
  "agent.report_out_of_window": "Отклонён отчёт: события вне окна",
  "agent.tasks_dispatched": "Выданы задачи станции",
  "agent.disabled": "Станция отключена",
  "agent.enabled": "Станция включена",
  "enrollment_token.create": "Выпущен токен регистрации",
  "operator.login": "Вход оператора",
  "operator.login_failed": "Неудачный вход оператора",
  "operator.login_throttled": "Вход заблокирован: слишком много попыток",
  "operator.password_change": "Смена пароля",
  "operator.password_change_failed": "Неудачная смена пароля",
  "operator.password_change_throttled": "Смена пароля заблокирована: слишком много попыток",
  "operator.sessions_revoked": "Завершены все сеансы оператора",
  "operator.created": "Создан оператор",
  "operator.role_changed": "Изменена роль оператора",
  "operator.disabled": "Оператор отключён",
  "operator.enabled": "Оператор включён",
  "operator.password_reset": "Сброшен пароль оператора",
  "request.window": "Запрос окна данных у станции",
  "policy.changed": "Изменена политика сервера",
  "policy.reset": "Политика сброшена к значениям сервера",
};

/**
 * Groups for the action filter: the part of a code before the first dot. The
 * server matches a bare group against every `group.*` code.
 */
export const ACTION_GROUPS: { value: string; label: string }[] = [
  { value: "operator", label: "Все действия операторов" },
  { value: "agent", label: "Все действия станций" },
  { value: "enrollment_token", label: "Токены регистрации" },
  { value: "request", label: "Запросы окон" },
  { value: "policy", label: "Изменения политики" },
];

/** Every known action as a single filter choice. */
export const ACTIONS: { value: string; label: string }[] = Object.entries(
  ACTION_LABELS,
).map(([value, label]) => ({ value, label }));

export function actionLabel(code: string): string {
  return ACTION_LABELS[code] ?? code;
}

function formatValue(value: unknown): string {
  return typeof value === "string" ? value : JSON.stringify(value);
}

/** One `key: value` line per entry; lists and objects as compact JSON. */
export function formatDetail(detail: Record<string, unknown>): string {
  const lines = Object.entries(detail).map(
    ([key, value]) => `${key}: ${formatValue(value)}`,
  );
  return lines.length > 0 ? lines.join("\n") : "—";
}

/**
 * An actor or target is an operator name, a station id, or a hostname. A
 * station id is shown as the station's hostname when the list is loaded;
 * anything else is shown as stored.
 */
export function resolveParty(value: string, stations: Agent[] | null): string {
  return stations?.find((station) => station.id === value)?.hostname ?? value;
}
