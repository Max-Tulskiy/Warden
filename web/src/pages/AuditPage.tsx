import { useEffect, useState, type FormEvent } from "react";

import { listAgents, listAudit, type AuditFilters } from "../api/client";
import type { Agent, AuditEntry } from "../api/types";
import { AppShell } from "../components/AppShell";
import { RangeFilter } from "../components/RangeFilter";
import {
  ACTION_GROUPS,
  ACTIONS,
  actionLabel,
  formatDetail,
  resolveParty,
} from "../lib/audit";
import { presetRange, resolveRange, type Preset } from "../lib/reportRange";
import { useAuth } from "../state/authContext";

// Matches the server's own DEFAULT_PAGE_SIZE
// (server/src/warden_server/schemas/report.py) -- if a page comes back full,
// there may be more to load.
const PAGE_SIZE = 500;

const LOAD_ERROR = "Не удалось загрузить журнал";

/** An actor or target, shown as a hostname when it is a known station id. */
function Party({ value, stations }: { value: string; stations: Agent[] | null }) {
  const shown = resolveParty(value, stations);
  return (
    <span className="mono" title={shown === value ? undefined : value}>
      {shown}
    </span>
  );
}

export function AuditPage() {
  const { token } = useAuth();
  const [preset, setPreset] = useState<Preset>("day");
  const [customStart, setCustomStart] = useState("");
  const [customEnd, setCustomEnd] = useState("");
  const [actor, setActor] = useState("");
  const [action, setAction] = useState("");
  const [stations, setStations] = useState<Agent[] | null>(null);

  // The filters of the query currently on screen. "Показать ещё" continues
  // this query, not whatever the form has been edited to since.
  const [applied, setApplied] = useState<AuditFilters | null>(null);
  const [entries, setEntries] = useState<AuditEntry[]>([]);
  const [hasMore, setHasMore] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);

  const showPage = (filters: AuditFilters, page: AuditEntry[], append: boolean) => {
    setApplied(filters);
    setEntries((previous) => (append ? [...previous, ...page] : page));
    setHasMore(page.length === PAGE_SIZE);
    setLoaded(true);
  };

  useEffect(() => {
    if (!token) return;
    let cancelled = false;

    const filters: AuditFilters = presetRange("day", new Date());
    listAudit(token, filters, { limit: PAGE_SIZE })
      .then((page) => {
        if (!cancelled) showPage(filters, page, false);
      })
      .catch(() => {
        if (!cancelled) setError(LOAD_ERROR);
      });
    // The station list only turns ids into hostnames; the log works without it.
    listAgents(token)
      .then((agents) => {
        if (!cancelled) setStations(agents);
      })
      .catch(() => undefined);

    return () => {
      cancelled = true;
    };
  }, [token]);

  const buildFilters = (): AuditFilters | null => {
    const resolved = resolveRange(preset, customStart, customEnd, new Date());
    if ("error" in resolved) {
      setFormError(resolved.error);
      return null;
    }
    return {
      ...resolved.range,
      actor: actor.trim() || undefined,
      action: action || undefined,
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
      showPage(filters, await listAudit(token, filters, { limit: PAGE_SIZE }), false);
    } catch {
      setError(LOAD_ERROR);
    }
  };

  const handleLoadMore = async () => {
    if (!token || !applied) return;
    setError(null);
    try {
      const page = await listAudit(token, applied, {
        limit: PAGE_SIZE,
        offset: entries.length,
      });
      showPage(applied, page, true);
    } catch {
      setError(LOAD_ERROR);
    }
  };

  return (
    <AppShell>
      <h1 style={{ margin: "0 0 20px 0", fontSize: 20, fontWeight: 700 }}>Журнал</h1>

      <form className="card report-filters" onSubmit={handleApply}>
        <RangeFilter
          preset={preset}
          customStart={customStart}
          customEnd={customEnd}
          onPresetChange={setPreset}
          onCustomStartChange={setCustomStart}
          onCustomEndChange={setCustomEnd}
        />

        <div className="filter-row">
          <label style={{ flex: 1 }}>
            Кто
            <input
              type="text"
              value={actor}
              maxLength={255}
              placeholder="Оператор, станция или имя хоста"
              onChange={(e) => setActor(e.target.value)}
            />
          </label>
          <label style={{ flex: 1 }}>
            Действие
            <select value={action} onChange={(e) => setAction(e.target.value)}>
              <option value="">Все действия</option>
              <optgroup label="Группы">
                {ACTION_GROUPS.map((group) => (
                  <option key={group.value} value={group.value}>
                    {group.label}
                  </option>
                ))}
              </optgroup>
              <optgroup label="Отдельные действия">
                {ACTIONS.map((item) => (
                  <option key={item.value} value={item.value}>
                    {item.label}
                  </option>
                ))}
              </optgroup>
            </select>
          </label>
        </div>

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
          Журнал фиксирует изменения и входы, но не чтение данных и не отказы отключённой
          станции. Он не защищён от правки средствами базы данных: запись может изменить
          тот, у кого есть доступ к БД.
        </p>
      </form>

      <section className="card" style={{ padding: "20px 0 4px 0", marginTop: 20 }}>
        <h2
          style={{ margin: "0 0 14px 0", padding: "0 22px", fontSize: 15, fontWeight: 600 }}
        >
          Записи
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
        {loaded && entries.length === 0 && (
          <p className="muted" style={{ padding: "0 22px" }}>
            За выбранный период записей нет.
          </p>
        )}
        {loaded && entries.length > 0 && (
          <table>
            <thead>
              <tr>
                <th style={{ width: "16%" }}>Время</th>
                <th style={{ width: "22%" }}>Действие</th>
                <th style={{ width: "14%" }}>Кто</th>
                <th style={{ width: "14%" }}>Объект</th>
                <th>Подробности</th>
              </tr>
            </thead>
            <tbody>
              {entries.map((entry) => (
                <tr key={entry.id}>
                  <td className="mono text-secondary">
                    {new Date(entry.occurred_at).toLocaleString("ru-RU")}
                  </td>
                  <td>
                    <span title={entry.action}>{actionLabel(entry.action)}</span>
                  </td>
                  <td style={{ overflowWrap: "anywhere" }}>
                    <Party value={entry.actor} stations={stations} />
                  </td>
                  <td style={{ overflowWrap: "anywhere" }}>
                    <Party value={entry.target} stations={stations} />
                  </td>
                  <td
                    className="mono text-secondary"
                    style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}
                  >
                    {formatDetail(entry.detail)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
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
