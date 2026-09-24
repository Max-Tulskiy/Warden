import type { Bounds, EditablePolicy } from "../api/types";

export type PolicyField = keyof EditablePolicy;

export function formatHours(hours: number): string {
  return `${hours} ч`;
}

export function formatMinutes(minutes: number): string {
  return minutes % 60 === 0 ? formatHours(minutes / 60) : `${minutes} мин`;
}

export function formatCount(count: number): string {
  return count.toLocaleString("ru-RU");
}

interface FieldInfo {
  key: PolicyField;
  label: string;
  /** The unit shown beside the input. */
  unit: string;
  /** How a value is written in a sentence, e.g. «8 ч». */
  format: (value: number) => string;
  /** The allowed range in words, e.g. «от 1 до 4 ч». */
  range: (bounds: Bounds) => string;
}

/** The three limits an administrator can change, in display order. */
export const POLICY_FIELDS: FieldInfo[] = [
  {
    key: "max_request_window_hours",
    label: "Максимальное окно запроса к агенту",
    unit: "ч",
    format: formatHours,
    range: (b) => `от ${b.min} до ${b.max} ч`,
  },
  {
    key: "enrollment_token_ttl_hours",
    label: "Срок действия токена регистрации",
    unit: "ч",
    format: formatHours,
    range: (b) => `от ${b.min} до ${b.max} ч`,
  },
  {
    key: "session_lifetime_minutes",
    label: "Срок действия сессии",
    unit: "мин",
    format: formatMinutes,
    range: (b) => `от ${formatMinutes(b.min)} до ${formatMinutes(b.max)}`,
  },
];

/**
 * Mirrors, but does not replace, the server's own check: the same whole-number
 * and range rules, so a mistake is named before anything is sent.
 */
export function validatePolicyForm(
  form: Record<PolicyField, string>,
  bounds: Record<PolicyField, Bounds>,
): { values: EditablePolicy } | { error: string } {
  const values: Partial<EditablePolicy> = {};
  for (const field of POLICY_FIELDS) {
    const text = form[field.key].trim();
    if (!/^\d+$/.test(text)) {
      return { error: `${field.label}: должно быть целое число` };
    }
    const value = Number(text);
    const range = bounds[field.key];
    if (value < range.min || value > range.max) {
      return { error: `${field.label}: допустимо ${field.range(range)}` };
    }
    values[field.key] = value;
  }
  return { values: values as EditablePolicy };
}
