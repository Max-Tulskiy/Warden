# Implementation plan: Deduplicate events delivered through overlapping window requests

**Spec:** [./spec.md](./spec.md) · **Status:** done · **Date:** 2026-09-22

---

## 1. Approach

Deduplication happens once, at ingestion, in
`server/src/warden_server/services/tasks.py::complete_task` — the only place
delivered events ever turn into `Event` rows. Before adding the incoming
batch, a new helper queries already-stored rows for the same `agent_id`
whose `occurred_at` matches one of the batch's timestamps, and drops any
incoming event whose `(category, occurred_at, payload)` exactly matches an
existing row. Only genuinely new occurrences are inserted. The task is
still marked `COMPLETED` regardless of how many of its events turned out to
already be known — including zero: the task did what was asked of it, and a
fully-duplicate answer is not a failure.

Matching is scoped to one `agent_id` (never merges occurrences across
stations, per spec A-5) and compares `category` and `payload` in Python
after narrowing candidates by the indexed `agent_id`/`occurred_at` columns —
this sidesteps writing dialect-specific JSON-equality SQL for SQLite's plain
`JSON` column versus PostgreSQL's `JSONB` (`db.py::json_column_type`).
Matching works because a genuine duplicate delivery is byte-identical: the
agent's buffer re-sends the same stored row verbatim to every task whose
window covers it (spec R-1's "same real-world occurrence" is, in practice,
the same buffered row read twice).

A new Alembic migration adds a composite index
`ix_events_agent_id_occurred_at` on `(agent_id, occurred_at)`. It backs the
new dedup lookup and also speeds up the existing daily-report query
(`daily_report` in `api/reports.py`, `WHERE agent_id = ? AND occurred_at
BETWEEN ...`), which today only benefits from the single-column
`ix_events_occurred_at` index added in `specs/002-panel-reports-and-settings/`.

`api/agents.py::submit_report`'s existing `agent.report` audit entry keeps
its `event_count` field (events submitted) and gains a `new_count` field
(events actually stored), so a suppressed duplicate is visible in the audit
trail at the same place the original delivery already is — no new audit
action, no new endpoint.

Constitution Section V's duplicate-events boundary (added in version 1.0.2
while planning `specs/002-panel-reports-and-settings/`) becomes false once
this ships and is removed via the amendment procedure (Section VII, PATCH).

## 2. Alternatives considered

| Option | Why rejected |
|---|---|
| A database-level `UNIQUE` constraint on `(agent_id, category, occurred_at, payload)` with `ON CONFLICT DO NOTHING` | Needs dialect-specific insert statements (`postgresql.insert()` vs. `sqlite.insert()`) instead of the plain `Session.add_all` used everywhere else in this codebase, to buy protection against a truly concurrent duplicate write this project's traffic profile does not produce: an agent answers one task at a time per poll, so two overlapping deliveries landing in the same instant is not realistic here. |
| Deduplicate at read time (`SELECT DISTINCT` / `GROUP BY` in `daily_report` and `fleet_report`) | Leaves every duplicate stored forever, so the table grows for no reason and every future reader of `events` — the two existing report endpoints and any later one — has to remember to deduplicate again. Storing the truth once, at ingestion, matches decision D-6's rationale for PostgreSQL ("relational integrity"). |
| Teach the agent to remember which buffered rows it already delivered, and skip them on a later answer | Contradicts D-1: the agent answers each task statelessly from its buffer, with no memory of past deliveries, which is what keeps it simple and keeps `agent.core` free of server-facing state. It also does not solve the actual scenario in spec.md's primary story — two *different* window requests, possibly placed by two different administrators, each independently triggering a delivery — since the agent has no way to know the server already has the data from a delivery to a *different* task. |

## 3. Constitution compliance

| Principle | How it is satisfied |
|---|---|
| 1. Platform code is isolated | Untouched — every change is server-only; no collector or `agent.core` code changes |
| 2. Data does not leave the buffer without a request | Untouched — dedup happens after the agent has already answered a `window_request` task; what triggers a delivery does not change |
| 3. Request window ≤ 4 hours | Untouched — no change to window validation |
| 4. Buffer retention is bounded | Untouched — agent-side buffer/pruning logic is not touched by this feature |
| 5. Exchange is authenticated and encrypted | Untouched — no new endpoint, no auth change |
| 6. Inventory is versioned separately | Untouched — inventory snapshots/changes are a distinct subsystem from category events |
| 7. Testable without real hardware | The dedup helper and the new index are pure server logic, covered by `server/tests/unit` (helper) and `server/tests/integration` (two overlapping requests through the real HTTP flow) against SQLite, per the existing pattern; migration reversibility is additionally checked by hand against real PostgreSQL (Section VI), the same way `ee7eb82ccbe5` was in `specs/002-panel-reports-and-settings/` |
| 8. Every action is logged | Extended, not just satisfied: the existing `agent.report` audit entry (`api/agents.py`) gains a `new_count` field alongside `event_count`, so a suppressed duplicate is visible in the log at the point of delivery |
| 9. Language mode | New code comments/docstrings in English; no new user-facing strings (deduplication is silent to both agent and administrator, spec R-5); doc updates split ru (canonical) / en (translation) as usual |
| 10. Honesty about boundaries | This feature removes a documented boundary rather than adding one; the constitution amendment and the doc updates (§4) delete the now-false "duplicate events" notes instead of leaving them stale |
| 11. The API contract is the source of truth | No request/response schema changes anywhere (`EventOut`/`ReportEventOut` already omit `task_id`; the audit `detail` blob is unstructured JSONB, outside the OpenAPI contract) — `contracts/openapi.yaml` is unchanged, verified by the existing contract-equality test |

**Violations:** none.

## 4. Affected modules

| Module | Change |
|---|---|
| `server/src/warden_server/services/tasks.py` | `complete_task` filters already-stored events out of the incoming batch before inserting |
| `server/src/warden_server/models/event.py` | new composite index `ix_events_agent_id_occurred_at` on `(agent_id, occurred_at)` |
| `server/alembic/versions/` | new migration adding that index |
| `server/src/warden_server/api/agents.py` | `submit_report`'s `agent.report` audit detail gains `new_count` |
| `.specify/memory/constitution.md` | Section V's duplicate-events bullet removed; version history row added (PATCH) |
| `docs/ru/architecture.md`, `docs/en/architecture.md` | boundaries section: drop the duplicate-events note |
| `docs/ru/usage.md`, `docs/en/usage.md` | drop the duplicate-events mention in the honest-status section |

No `agent/` or `web/` changes — deduplication is invisible on both sides of
the API (§5, §6).

## 5. Data formats

No new or changed Pydantic schema, no new endpoint, and no change to
`contracts/openapi.yaml`: `EventOut` and `ReportEventOut` do not expose
`task_id`, so which task an occurrence was first stored under is not
API-visible, and dropping a duplicate changes only which rows exist, not
their shape. The one data change is the new database index (§4) and the
widened `detail` JSON on the existing `agent.report` audit row — audit
`detail` is unstructured JSONB, not part of the contract.

## 6. Interface

No web panel change. `ReportsPage.tsx` and the daily-report view already
show whatever `GET /api/v1/agents/{id}/events` and `GET /api/v1/events`
return; with duplicates no longer stored, both simply show fewer, correct
rows without any code change on the panel side.

## 7. Risks

| Risk | Mitigation |
|---|---|
| The pre-insert lookup grows expensive as an `events` table accumulates history | Narrowed by the new composite index and by only ever querying the `occurred_at` values present in the current batch (bounded by `MAX_REPORT_EVENTS`), never a full-table scan; lab-scale event volume keeps this cheap |
| Comparing JSON payloads in Python assumes a duplicate delivery serializes identically to the first one | True by construction here: the agent's buffer re-sends the same stored row verbatim (no payload is regenerated between deliveries), so a genuine duplicate is byte-identical; documented as the definition of "same occurrence" in `spec.md` |
| A genuinely new, distinct occurrence coincidentally matches an old one's `(category, occurred_at, payload)` | Astronomically unlikely at datetime precision for realistic payloads (a PID+process name, a URL+title, a device serial); matching is additionally scoped to one station (spec A-5), narrowing the collision space further |

## 8. Verification plan

```bash
cd server && pytest tests/unit/test_services/test_tasks.py -k dedup
cd server && pytest tests/integration/test_window_request -k overlap
cd server && ruff check . && ruff format --check . && mypy src alembic \
  && bandit -c pyproject.toml -r src && pytest
```

Checked in CI, no real hardware needed (principle 7): the dedup helper
against SQLite fixtures covering exact-match, partial-overlap, and
distinct-payload-at-the-same-timestamp cases (spec A-1 through A-5); the
full HTTP flow (place two overlapping requests, agent answers both, report
shows one row) as a `server/tests/integration` test reusing the existing
`test_window_request` fixtures.

Checked by hand before this ships (Section VI, no agent/platform-collector
code involved so nothing beyond the migration needs a live device): the new
migration's `upgrade` / `downgrade` / `upgrade` cycle against a real
PostgreSQL instance via a throwaway `docker compose` project, the same
procedure used for `ee7eb82ccbe5` in `specs/002-panel-reports-and-settings/`.
