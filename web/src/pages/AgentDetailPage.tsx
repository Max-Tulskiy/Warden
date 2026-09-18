import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { getEvents, getInventoryChanges, requestWindow } from "../api/client";
import type { EventRecord, InventoryChange } from "../api/types";
import { AppShell } from "../components/AppShell";
import { ChangeTimeline } from "../components/ChangeTimeline";
import { EventList } from "../components/EventList";
import { BackArrowIcon } from "../components/icons";
import { WindowRequestForm } from "../components/WindowRequestForm";
import { useAuth } from "../state/authContext";

function today(): string {
  return new Date().toISOString().slice(0, 10);
}

export function AgentDetailPage() {
  const { agentId } = useParams<{ agentId: string }>();
  const { token } = useAuth();
  const [reportDate, setReportDate] = useState(today());
  const [events, setEvents] = useState<EventRecord[]>([]);
  const [changes, setChanges] = useState<InventoryChange[]>([]);
  const [requestMessage, setRequestMessage] = useState<string | null>(null);

  const loadEvents = () => {
    if (!token || !agentId) return;
    getEvents(token, agentId, reportDate).then(setEvents);
  };

  useEffect(loadEvents, [token, agentId, reportDate]);

  useEffect(() => {
    if (!token || !agentId) return;
    getInventoryChanges(token, agentId).then(setChanges);
  }, [token, agentId]);

  const handleWindowRequest = async (windowStart: string, windowEnd: string) => {
    if (!token || !agentId) return;
    await requestWindow(token, agentId, windowStart, windowEnd);
    setRequestMessage(
      "Запрос поставлен в очередь: агент ответит на очередном сеансе связи с сервером.",
    );
  };

  if (!agentId) return null;

  return (
    <AppShell narrow>
      <div style={{ marginBottom: 4 }}>
        <Link
          to="/agents"
          className="text-secondary"
          style={{ fontSize: 13, display: "inline-flex", alignItems: "center", gap: 6 }}
        >
          <BackArrowIcon /> к списку станций
        </Link>
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 24 }}>
        <h1 className="mono" style={{ margin: 0, fontSize: 20, fontWeight: 700 }}>
          {agentId}
        </h1>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
        <section className="card">
          <h2 style={{ margin: "0 0 14px 0", fontSize: 15, fontWeight: 600 }}>
            Запросить данные за промежуток
          </h2>
          <WindowRequestForm onSubmit={handleWindowRequest} />
          {requestMessage && (
            <p className="muted" style={{ marginBottom: 0 }}>
              {requestMessage}
            </p>
          )}
        </section>

        <section className="card" style={{ padding: "20px 0 4px 0" }}>
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              padding: "0 22px",
              marginBottom: 14,
            }}
          >
            <h2 style={{ margin: 0, fontSize: 15, fontWeight: 600 }}>Отчёт за день</h2>
            <input
              type="date"
              value={reportDate}
              onChange={(e) => setReportDate(e.target.value)}
              style={{ width: 160 }}
            />
          </div>
          <EventList events={events} />
        </section>

        <section className="card">
          <h2 style={{ margin: "0 0 16px 0", fontSize: 15, fontWeight: 600 }}>
            Изменения конфигурации
          </h2>
          <ChangeTimeline changes={changes} />
        </section>
      </div>
    </AppShell>
  );
}
