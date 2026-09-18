import { useState } from "react";

import { validateWindow } from "../lib/windowValidation";

interface WindowRequestFormProps {
  onSubmit: (windowStart: string, windowEnd: string) => Promise<void>;
}

export function WindowRequestForm({ onSubmit }: WindowRequestFormProps) {
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    const validationError = validateWindow(start, end);
    if (validationError) {
      setError(validationError);
      return;
    }
    setError(null);
    setSubmitting(true);
    try {
      await onSubmit(new Date(start).toISOString(), new Date(end).toISOString());
    } catch {
      setError("Сервер отклонил запрос");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <form onSubmit={handleSubmit}>
      <div style={{ display: "flex", alignItems: "flex-end", gap: 14 }}>
        <label style={{ flex: 1 }}>
          Начало
          <input
            type="datetime-local"
            value={start}
            onChange={(e) => setStart(e.target.value)}
            required
          />
        </label>
        <label style={{ flex: 1 }}>
          Конец
          <input
            type="datetime-local"
            value={end}
            onChange={(e) => setEnd(e.target.value)}
            required
          />
        </label>
        <button className="btn-primary" type="submit" disabled={submitting}>
          {submitting ? "Отправка..." : "Запросить данные"}
        </button>
      </div>
      {error ? (
        <p className="error" style={{ marginTop: 10, marginBottom: 0 }}>
          {error}
        </p>
      ) : (
        <p className="field-hint" style={{ marginBottom: 0 }}>
          Промежуток не должен превышать 4 часов
        </p>
      )}
    </form>
  );
}
