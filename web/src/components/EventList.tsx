import type { EventRecord } from "../api/types";
import { CategoryTag } from "./CategoryTag";

function summarize(event: EventRecord): string {
  switch (event.category) {
    case "removable_media":
      return `USB-накопитель ${event.payload.device} — ${
        event.payload.action === "connected" ? "подключён" : "отключён"
      }`;
    case "printing":
      return `${event.payload.job_name} → ${event.payload.printer} (${event.payload.user})`;
    case "processes":
      return `${event.payload.name} (pid ${event.payload.pid})`;
    case "web":
      return `${event.payload.title ?? event.payload.url}`;
    default:
      return JSON.stringify(event.payload);
  }
}

export function EventList({ events }: { events: EventRecord[] }) {
  if (events.length === 0) {
    return <p className="muted">За выбранный день данных нет.</p>;
  }

  return (
    <table>
      <thead>
        <tr>
          <th style={{ width: "14%" }}>Время</th>
          <th style={{ width: "18%" }}>Категория</th>
          <th>Событие</th>
        </tr>
      </thead>
      <tbody>
        {events.map((event) => (
          <tr key={event.id}>
            <td className="mono text-secondary">
              {new Date(event.occurred_at).toLocaleTimeString("ru-RU")}
            </td>
            <td>
              <CategoryTag category={event.category} />
            </td>
            <td>{summarize(event)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
