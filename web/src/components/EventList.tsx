import { Link } from "react-router-dom";

import type { EventRecord, FleetEvent } from "../api/types";
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

interface EventListProps {
  events: (EventRecord | FleetEvent)[];
  /** Adds a station column and a full date, for reports spanning stations and days. */
  showStation?: boolean;
  emptyMessage?: string;
}

export function EventList({
  events,
  showStation = false,
  emptyMessage = "За выбранный день данных нет.",
}: EventListProps) {
  if (events.length === 0) {
    return (
      <p className="muted" style={{ padding: "0 22px" }}>
        {emptyMessage}
      </p>
    );
  }

  return (
    <table>
      <thead>
        <tr>
          <th style={{ width: showStation ? "18%" : "14%" }}>Время</th>
          {showStation && <th style={{ width: "16%" }}>Станция</th>}
          <th style={{ width: showStation ? "16%" : "18%" }}>Категория</th>
          <th>Событие</th>
        </tr>
      </thead>
      <tbody>
        {events.map((event) => (
          <tr key={event.id}>
            <td className="mono text-secondary">
              {showStation
                ? new Date(event.occurred_at).toLocaleString("ru-RU")
                : new Date(event.occurred_at).toLocaleTimeString("ru-RU")}
            </td>
            {showStation && (
              <td>
                {"hostname" in event && (
                  <Link
                    to={`/agents/${event.agent_id}`}
                    className="mono"
                    style={{ fontWeight: 500 }}
                  >
                    {event.hostname}
                  </Link>
                )}
              </td>
            )}
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
