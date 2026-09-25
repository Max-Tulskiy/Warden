# Implementation plan: Record who views collected data and the audit log

**Spec:** [./spec.md](./spec.md) · **Status:** done · **Date:** 2026-09-25

---

## 1. Approach

Four handlers record their own use: `daily_report`, `fleet_report`, and
`inventory_changes` in `server/src/warden_server/api/reports.py`, and
`audit_log` in `server/src/warden_server/api/audit.py`. Each gains an
`operator` parameter (`Depends(require_operator)`, and `Depends(require_admin)`
for the audit log) so the handler knows who is asking. Both routers already
declare the same dependency for the whole router, and FastAPI resolves a
dependency once per request, so the parameter only exposes the object that
was already resolved; the router-wide declarations stay, which leaves the
handlers that are not audited (`list_agents`, `get_policy`, the operator
list) exactly as they are.

**The entry is written and committed before the query runs.** Each handler
calls `log_event(...)` and `db.commit()` first, then reads and returns the
data. This gives three things at once:

* a view is never answered without its entry (spec R-5): a failed write
  raises and nothing has been read;
* no ORM row is loaded before the commit, so SQLAlchemy's default
  `expire_on_commit=True` cannot turn the returned rows (up to
  `MAX_PAGE_SIZE`) into one lazy reload each — no change to `db.py` or to
  the test session is needed;
* a rejected request leaves no entry (spec R-6) with no extra code:
  dependency failures (401, 403) and parameter validation (422) all happen
  before the handler body runs.

**Action codes** form a new dotted group, `view`: `view.daily_report`,
`view.fleet_report`, `view.inventory_changes`, `view.audit_log`. The audit
log's existing group matching (`action=view` matches every `view.*` and
nothing else) already serves spec R-7 without a server change, and the
`operator` group — sign-ins and account changes — does not match them.

**What each entry says** (spec R-2, R-3): `target` is the station id for
`daily_report` and `inventory_changes` (the panel already shows a station id
as its hostname), and the fixed words `fleet` and `audit_log` for the two
views that span stations or the log. `detail` carries the request's own
parameters, as text: `report_date`, `limit`, `offset` for the daily report;
`start`, `end`, `agent_id` (the list asked for, possibly empty), `category`
(or null), `limit`, `offset` for the fleet report; `limit`, `offset` for the
inventory history; `start`, `end`, `actor`, `action`, `limit`, `offset` for
the audit log. An `offset` above zero is what marks a later page.

The four handlers' docstrings feed the OpenAPI descriptions, and
`audit_log`'s currently says "Reading the log is not itself recorded in it,
like every other read." — false after this change. They are rewritten, and
`contracts/openapi.yaml` is regenerated with the handler change (constitution
principle 11).

**Panel.** `web/src/lib/audit.ts` gains four Russian labels and a
`{ value: "view", label: "Просмотры данных" }` entry in `ACTION_GROUPS`;
the hint under the filters in `web/src/pages/AuditPage.tsx`, which now says
the log does not record reads, is rewritten to say what is and is not
recorded.

**Constitution.** A new decision, **D-12** — views of collected data and of
the log are recorded, before they are answered — and the Section V boundary
on unrecorded reads is rewritten to say which reads are and are not
recorded. The decision is needed because the scope is a real fork (which
reads, in which order, under which name) with alternatives rejected in §2;
adding a decision is a MINOR amendment, so **1.4.0**.

## 2. Alternatives considered

| Option | Why rejected |
|---|---|
| Record every operator read, including the station list, the policy, the list of operators, and the session check | The panel fetches the station list as a helper on four screens (stations, reports, settings, the audit log's hostname lookup); an entry per call would bury the views that matter under near-meaningless rows. |
| Record after the query, as one commit at the end of each handler | Loads the rows first and commits second, so the default `expire_on_commit=True` reloads every returned row lazily (a real N+1 for pages of up to 2000 rows); and a failed write would come after the data had already been read. |
| Set `expire_on_commit=False` on the shared session to make recording-after-reading cheap | A session-wide behavior change to avoid choosing a better order in four handlers; writing first needs no setting. |
| Name the entries `operator.view_*` | The `operator` group is what an administrator filters by to watch sign-ins and account changes; putting views there would fill it with routine reading. |
| A middleware that records every `GET` | Cannot say what was viewed (a report's day, the filters) without parsing each route's parameters again, and would include the reads decided out of scope. |
| Record only the first page of a paged view | Each page is a separate disclosure of different rows; the `offset` in `detail` lets a reader group pages, which a missing entry would not. |
| A separate table for views | A second place to read for "who did what"; the audit log screen, its filter, and its endpoint already fit these entries, and the `view` group keeps them apart. |

## 3. Constitution compliance

| Principle | How it is satisfied |
|---|---|
| 1. Platform code is isolated | Untouched — server and panel only |
| 2. Data does not leave the buffer without a request | Untouched — nothing about what agents send changes |
| 3. Request window ≤ 4 hours | Untouched — these are reads of stored data, like the existing reports |
| 4. Buffer retention is bounded | Untouched |
| 5. Exchange is authenticated and encrypted | Unchanged: the actor written to an entry is the operator `require_operator` verified on that request; a request that fails authentication or the role check never reaches the recording code |
| 6. Inventory is versioned separately | Untouched — only the reading of the change history is recorded |
| 7. Testable without real hardware | Server behavior (entries, refusals, the group filter, the failed-write case) is tested through the real HTTP endpoints against an in-memory database; the panel's labels and hint are `vitest` unit tests |
| 8. Every action is logged | Extended. Principle 8's list names actions that change or authenticate; D-12 records that an operator's view of collected data or of the log is an action of the same kind, and the entries are written by the same `log_event` |
| 9. Language mode | Code comments and docstrings in English; the panel's new labels and hint in Russian; documentation ru (canonical) and en (translation) |
| 10. Honesty about boundaries | The Section V boundary on unrecorded reads is rewritten to say exactly what is now recorded and what is still not (station list, policy, operator list, session check, rejected requests), so the remaining gap is stated rather than implied closed |
| 11. The API contract is the source of truth | No request or response schema changes; the descriptions of four endpoints do, so `contracts/openapi.yaml` is regenerated and committed with the handler change |

**Violations:** none. The added decision (D-12) and the rewritten boundary go
through Section VII as a MINOR amendment, 1.4.0.

## 4. Affected modules

| Module | Change |
|---|---|
| `server/src/warden_server/api/reports.py` | `daily_report`, `fleet_report`, `inventory_changes` record a view before reading; docstrings updated |
| `server/src/warden_server/api/audit.py` | `audit_log` records a view before reading; docstring updated |
| `contracts/openapi.yaml` | regenerated (descriptions of the four endpoints) |
| `web/src/lib/audit.ts` | four labels, the `view` group |
| `web/src/pages/AuditPage.tsx` | the hint under the filters |
| `.specify/memory/constitution.md` | D-12; Section V boundary rewritten; version 1.4.0 and its history row |
| `docs/ru/architecture.md`, `docs/en/architecture.md` | the audit log section and the Section V mirror list |
| `docs/ru/usage.md`, `docs/en/usage.md` | the audit log paragraph; what was verified by hand |

No `agent/` change, no migration, no new endpoint, no new schema.

## 5. Data formats

| Action code | `target` | `detail` |
|---|---|---|
| `view.daily_report` | station id | `report_date`, `limit`, `offset` |
| `view.fleet_report` | `fleet` | `start`, `end`, `agent_id` (list of ids, may be empty), `category` (or null), `limit`, `offset` |
| `view.inventory_changes` | station id | `limit`, `offset` |
| `view.audit_log` | `audit_log` | `start`, `end`, `actor` (or null), `action` (or null), `limit`, `offset` |

`actor` on every entry is the operator's username. `detail` is unstructured
JSON, outside the API contract, like every other entry's. No column, table,
or schema changes.

## 6. Interface

In the audit log screen: the action filter gains a group, "Просмотры данных",
and the four codes are individually selectable under Russian names; an entry
for a view shows its parameters through the existing detail column. The hint
under the filters is rewritten to say that changes, sign-ins, and views of
collected data and of the log are recorded, and that the station list, the
policy, the list of operators, and rejected requests are not. No new screen
and no other change.

## 7. Risks

| Risk | Mitigation |
|---|---|
| The audit log grows by a row per view, and the audit screen's own fetches (each filter change or "show more") add rows about themselves | No timer polls any of the four endpoints, so growth tracks operator activity; the `view` group lets a reader filter the views out; there is no retention for the log today, stated in the docs rather than solved here |
| The entry for the view being displayed can appear in that same response (written before the read) | Harmless and truthful; documented in the audit log paragraph so it is not read as a fault |
| A failed write now fails a read (spec R-5, deliberately fail-closed) | Acceptable for a single-node deployment where the same database serves both; covered by a test that makes the write fail and asserts no data is returned |
| One extra commit per view | One small insert per request, no more than the entries the existing write actions already make |
| Tests that order audit rows by `id` — a random UUID here, with no chronological meaning | Tests order by `occurred_at`, the lesson from `specs/007-event-deduplication/` |

## 8. Verification plan

```bash
cd server && pytest tests/integration/test_read_audit
cd server && ruff check . && ruff format --check . && mypy src alembic \
  && bandit -c pyproject.toml -r src && pytest
cd web && npm run lint && npm run format && npm test && npm run build
```

Checked in CI, no real hardware needed (principle 7): each of the four views
adds one entry with the right actor, code, target, and detail; an observer's
view is recorded and an observer's request for the audit log is refused
without an entry; a request with no session or with invalid parameters adds
nothing; the station list, the policy, and the list of operators add
nothing; a repeated view and a later page each add their own entry; the
`view` group filter returns only views and the `operator` group returns none;
a failed write returns no data. The contract-equality test confirms the
regenerated contract; the panel's labels, group, and hint are `vitest` tests.

Checked by hand before this ships (Section VI): a pass on the real compose
stack (Caddy and PostgreSQL, a throwaway project on remapped ports because
the user's `gitlab` container holds 80 and 443) — sign in as an
administrator, create an observer, view a report and an inventory history as
each, open the audit log, and confirm the entries, the group filter, and the
hint in a real browser. What that does not prove (one browser, a script
standing in for agents) is stated in `docs/*/usage.md`.
