import { useEffect, useState, type FormEvent } from "react";

import { getFleetEvents, listAgents, type FleetFilters } from "../api/client";
import type { Agent, FleetEvent } from "../api/types";
import { AppShell } from "../components/AppShell";
import { EventList } from "../components/EventList";
import { CATEGORIES, CATEGORY_LABELS, type EventCategory } from "../lib/categories";
import { presetRange, validateReportRange, type RangePreset } from "../lib/reportRange";
import { useAuth } from "../state/authContext";

// Matches the server's own DEFAULT_PAGE_SIZE
// (server/src/warden_server/schemas/report.py) -- if a page comes back full,
// there may be more to load.
const PAGE_SIZE = 500;

type Preset = RangePreset | "custom";

const PRESETS: { value: Preset; label: string }[] = [
  { value: "hour", label: "Последний час" },
  { value: "day", label: "Последние 24 часа" },
  { value: "week", label: "Последние 7 дней" },
  { value: "custom", label: "Свой период" },
];

const LOAD_ERROR = "Не удалось загрузить отчёт";

export function ReportsPage() {
  const { token } = useAuth();
  const [preset, setPreset] = useState<Preset>("day");
  const [customStart, setCustomStart] = useState("");
  const [customEnd, setCustomEnd] = useState("");
  const [selectedAgentIds, setSelectedAgentIds] = useState<string[]>([]);
  const [category, setCategory] = useState<EventCategory | "">("");
  const [stations, setStations] = useState<Agent[] | null>(null);

  // The filters of the query currently on screen. "Показать ещё" continues
  // this query, not whatever the form has been edited to since.
  const [applied, setApplied] = useState<FleetFilters | null>(null);
  const [events, setEvents] = useState<FleetEvent[]>([]);
  const [hasMore, setHasMore] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);

  const showPage = (filters: FleetFilters, page: FleetEvent[], append: boolean) => {
    setApplied(filters);
    setEvents((previous) => (append ? [...previous, ...page] : page));
    setHasMore(page.length === PAGE_SIZE);
    setLoaded(true);
  };

  useEffect(() => {
    if (!token) return;
    let cancelled = false;

    const filters: FleetFilters = presetRange("day", new Date());
    getFleetEvents(token, filters, { limit: PAGE_SIZE })
      .then((page) => {
        if (!cancelled) showPage(filters, page, false);
      })
      .catch(() => {
        if (!cancelled) setError(LOAD_ERROR);
      });
    // The station list only feeds the filter; the report works without it.
    listAgents(token)
      .then((agents) => {
        if (!cancelled) setStations(agents);
      })
      .catch(() => {
        if (!cancelled) setStations([]);
      });

    return () => {
      cancelled = true;
    };
  }, [token]);

  const buildFilters = (): FleetFilters | null => {
    let range: { start: string; end: string };
    if (preset === "custom") {
      const problem = validateReportRange(customStart, customEnd);
      if (problem) {
        setFormError(problem);
        return null;
      }
      range = {
        start: new Date(customStart).toISOString(),
        end: new Date(customEnd).toISOString(),
      };
    } else {
      range = presetRange(preset, new Date());
    }
    return {
      ...range,
      agentIds: selectedAgentIds,
      category: category || undefined,
    };
  };

  const handleApply = async (event: FormEvent) => {
    event.preventDefault();
    setFormError(null);
    if (!token) return;
    const filters = buildFilters();
    if (!filters) return;

    setError(null);
    setLoaded(false);
    try {
      showPage(filters, await getFleetEvents(token, filters, { limit: PAGE_SIZE }), false);
    } catch {
      setError(LOAD_ERROR);
    }
  };

  const handleLoadMore = async () => {
    if (!token || !applied) return;
    setError(null);
    try {
      const page = await getFleetEvents(token, applied, {
        limit: PAGE_SIZE,
        offset: events.length,
      });
      showPage(applied, page, true);
    } catch {
      setError(LOAD_ERROR);
    }
  };

  const toggleStation = (agentId: string) => {
    setSelectedAgentIds((current) =>
      current.includes(agentId)
        ? current.filter((id) => id !== agentId)
        : [...current, agentId],
    );
  };

  return (
    <AppShell>
      <h1 style={{ margin: "0 0 20px 0", fontSize: 20, fontWeight: 700 }}>Отчёты</h1>

      <form className="card report-filters" onSubmit={handleApply}>
        <div className="segmented" role="group" aria-label="Период">
          {PRESETS.map((item) => (
            <button
              key={item.value}
              type="button"
              className={preset === item.value ? "segmented-item active" : "segmented-item"}
              aria-pressed={preset === item.value}
              onClick={() => setPreset(item.value)}
            >
              {item.label}
            </button>
          ))}
        </div>

        {preset === "custom" && (
          <div className="filter-row">
            <label style={{ flex: 1 }}>
              Начало
              <input
                type="datetime-local"
                value={customStart}
                onChange={(e) => setCustomStart(e.target.value)}
              />
            </label>
            <label style={{ flex: 1 }}>
              Конец
              <input
                type="datetime-local"
                value={customEnd}
                onChange={(e) => setCustomEnd(e.target.value)}
              />
            </label>
          </div>
        )}

        <div className="filter-row">
          <label style={{ minWidth: 220 }}>
            Категория
            <select
              value={category}
              onChange={(e) => setCategory(e.target.value as EventCategory | "")}
            >
              <option value="">Все категории</option>
              {CATEGORIES.map((value) => (
                <option key={value} value={value}>
                  {CATEGORY_LABELS[value]}
                </option>
              ))}
            </select>
          </label>
        </div>

        <fieldset className="station-filter">
          <legend>Станции</legend>
          {stations?.map((station) => (
            <label key={station.id} className="check">
              <input
                type="checkbox"
                checked={selectedAgentIds.includes(station.id)}
                onChange={() => toggleStation(station.id)}
              />
              {station.hostname}
            </label>
          ))}
          {stations && stations.length === 0 && (
            <span className="muted">Нет зарегистрированных станций</span>
          )}
          <span className="field-hint" style={{ margin: 0 }}>
            Если ничего не выбрано, берутся все станции.
          </span>
        </fieldset>

        <div className="filter-actions">
          <button className="btn-primary" type="submit">
            Показать
          </button>
        </div>
        {formError && (
          <p className="error" style={{ margin: 0 }}>
            {formError}
          </p>
        )}
        <p className="field-hint" style={{ margin: 0 }}>
          Показаны только события, которые станции передали по запросам окна. Активность вне
          запрошенных окон здесь не видна.
        </p>
      </form>

      <section className="card" style={{ padding: "20px 0 4px 0", marginTop: 20 }}>
        <h2
          style={{ margin: "0 0 14px 0", padding: "0 22px", fontSize: 15, fontWeight: 600 }}
        >
          События
        </h2>
        {error && (
          <p className="error" style={{ padding: "0 22px" }}>
            {error}
          </p>
        )}
        {!loaded && !error && (
          <p className="text-secondary" style={{ padding: "0 22px" }}>
            Загрузка...
          </p>
        )}
        {loaded && (
          <EventList
            events={events}
            showStation
            emptyMessage="За выбранный период данных нет."
          />
        )}
        {hasMore && (
          <div style={{ padding: "14px 22px 16px 22px" }}>
            <button className="btn-secondary" type="button" onClick={handleLoadMore}>
              Показать ещё
            </button>
          </div>
        )}
      </section>
    </AppShell>
  );
}
