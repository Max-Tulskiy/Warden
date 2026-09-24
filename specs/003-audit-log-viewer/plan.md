# Implementation plan: Audit log viewer

**Spec:** [./spec.md](./spec.md) · **Status:** done · **Date:** 2026-09-24

---

## 1. Approach

Two slices, server then panel. **No agent source changes** and no new
audited action: the log is already written at every mutating endpoint; this
feature only reads it.

### Slice A — server: `GET /api/v1/audit` (R-1, R-4…R-6, R-8, R-9)

* A new read endpoint in a new `api/audit.py`, registered in `main.py`. Its
  router carries `dependencies=[Depends(require_operator)]`, like `reports`
  and `policy`, so no handler can forget authentication (R-9). When roles
  arrive, that one line is the only place to narrow it.
* Inputs are a Pydantic query model, `AuditFilter` (`schemas/audit.py`), bound
  with `Annotated[AuditFilter, Query()]` as `ReportFilter` is:
  * `start`, `end` (required), rejected when `end <= start` (A-2) and
    normalized to UTC before comparison — exactly the behavior of
    `ReportFilter`. Rather than copy the two validators, both filters now
    inherit them from a small base class, `TimeRange` (`schemas/timerange.py`).
    It carries only `start` and `end`, so the field order of the existing
    `/events` query parameters is unchanged and `contracts/openapi.yaml` does
    not move for that path.
  * `actor` (optional, exact match, 1–255 characters).
  * `action` (optional, 1–64 characters of `[a-z0-9_.]`), matched as **an exact
    action code or a dotted group**: `operator.login` matches only that code;
    `operator` matches every `operator.*`. The predicate is
    `action == value OR action LIKE value || '.%'` with `autoescape=True`.
    A plain string prefix would make `operator.login` also match
    `operator.login_failed` and `operator.login_throttled`, which is not what
    an administrator filtering on "logins" means (R-6).
  * `limit` / `offset` with `DEFAULT_PAGE_SIZE` / `MAX_PAGE_SIZE` from
    `schemas/report.py`, where 002 put them (R-8).
* The response is `list[AuditEntryOut]`: `id`, `actor`, `action`, `target`,
  `occurred_at`, `detail` (`from_attributes`, like `AgentOut`). `action` stays
  a plain `str`, not an enum: rows written by an older or newer server must
  still be readable (R-7 on the panel side).
* Order is `(occurred_at DESC, id)`; `id` is the tie-break that keeps offset
  paging free of loss and repeats when entries share a timestamp (A-5). The
  range is half-open `[start, end)`, as in the fleet report.
* An Alembic revision (down-revision `ee7eb82ccbe5`) adds
  `ix_audit_log_occurred_at` on `audit_log(occurred_at)`, mirrored in
  `AuditLogEntry.__table_args__` the way `Event` declares its index. Without
  it every range read scans the whole log, which only grows.
* Reads are not audited (spec §5). A test asserts the row count is unchanged
  by a read, so the choice is pinned rather than accidental.

### Slice B — panel: «Журнал» (R-1…R-8)

* Nav item «Журнал» in `AppShell.tsx`, route `/audit`, page `AuditPage.tsx`.
* The preset segmented control and the custom start/end inputs are lifted out
  of `ReportsPage.tsx` into `components/RangeFilter.tsx`, a controlled
  component, and used by both pages. `ReportsPage` behavior does not change;
  its existing tests are the regression guard, and this step is done first,
  green on its own. `presetRange` and `validateReportRange` from
  `lib/reportRange.ts` are reused as they are.
* Filters: actor (text input, empty means all) and action (a select with
  «Все действия», a group of dotted-group choices, and every known action).
  The default range is the last 24 hours. As on the report screen, "Показать
  ещё" continues the query on screen, not what the form has been edited to
  since, and appears when a page comes back full.
* `lib/audit.ts` holds the Russian names of the 17 action codes the server
  emits today, the four groups, and two formatters. An unknown code falls back
  to itself (R-7, A-7). `detail` renders as `key: value` pairs, with a list or
  object value shown as compact JSON; an empty `detail` shows «—».
* Actor and target of station actions are UUIDs. The page already can list
  stations (`listAgents`, as `ReportsPage` does), so a value that equals a
  known station id is shown as the hostname, with the raw id in the tooltip.
  If the station list fails to load, raw ids show; the log itself does not
  depend on it.
* All values are rendered as React text, never as HTML (see §7).

### Spec points this plan resolves

1. **"Group of related actions" (R-6)** becomes the dotted-namespace rule
   above. The four groups today: `operator`, `agent`, `enrollment_token`,
   `request`.
2. **"Who performed it" (R-3)** is three different kinds of value in the log:
   an operator username, a station id, or — for `agent.enroll` and
   `agent.enroll_rejected` — the hostname the caller announced. The page shows
   each as stored, resolving only station ids to hostnames.
3. **Default range** is 24 hours, like the report screen; presets are
   computed when applied, not when the page loads.

### Order of work

Slice A (unit tests → integration tests → migration → schemas and endpoint →
contract) → Slice B (`RangeFilter` extraction → client → `lib/audit.ts` →
page → nav) → docs and the constitution PATCH.

## 2. Alternatives considered

| Option | Why rejected |
|---|---|
| Plain string prefix for the action filter | `operator.login` would also return failed and throttled logins; an exact-or-dotted-group rule costs one `OR` and matches how the codes are named |
| Make `action` a server-side enum in the response | An unknown code from a different server version would fail response validation and hide the entry; R-7 requires the opposite |
| A separate endpoint listing known actions for the filter | Seventeen labels are a panel concern (they are Russian UI text, principle 9); a second endpoint would add contract surface for a constant list |
| Copy `ReportFilter`'s validators into `AuditFilter` | Two copies of the naive/aware UTC rule can drift; the mixed naive/aware `TypeError` was a real hazard that 002 had to fix once |
| Extract the whole paged-query state (preset, applied filters, load more) into a shared hook | The two pages differ in filters, rows, and messages; sharing only the range control removes the duplicated markup without forcing one abstraction over both |
| Keyset pagination | Same reasoning as 002: the panel and every existing endpoint page with `limit`/`offset` |
| Audit the reads of the log | Not done for any other read; would make opening the screen grow the log. Kept as a stated boundary, not decided silently |
| Show entries as they arrive (polling or push) | Out of scope (spec §5); adds moving rows under an offset-paged table |

## 3. Constitution compliance

| Principle | How it is satisfied |
|---|---|
| 1. Platform code is isolated | No OS-dependent code. The touched server files are checked with the principle's grep for `sys.platform` / `platform.system` and platform imports |
| 2. Data does not leave the buffer without a request | Unchanged agent and transport. The log is server-side data about actions; nothing is pulled from a workstation |
| 3. Request window ≤ 4 hours | Not touched. Like the fleet report, a log range is a read of stored rows, not a window request; a test asserts a 30-day range succeeds |
| 4. Buffer retention is bounded | Not touched (no agent change) |
| 5. Exchange is authenticated and encrypted | The router requires an operator token; a test asserts 401 without one. TLS unchanged (Caddy) |
| 6. Inventory is versioned | Not touched |
| 7. Logic is testable without real hardware | In-memory SQLite fixtures in `tests/conftest.py`; panel tests in `vitest`. No device, privilege, or network |
| 8. Every action is logged | No new mutating endpoint, so no new `log_event`. **Interpretation, kept consistent with 002:** the read of the log is not itself audited, as no read is. This is stated in the docs and in the constitution PATCH below |
| 9. Language mode | Docstrings and comments English; action names, labels, hints, and errors in the panel Russian; `docs/ru` canonical, `docs/en` in sync in the same change |
| 10. Honesty about boundaries | See below |
| 11. API contract is the single source of truth | `contracts/openapi.yaml` regenerated from `app.openapi()` with the endpoint; the equality test fails on drift. The `TimeRange` refactor must leave the `/events` part byte-identical, which the same test proves |

Principle 10, concretely. A viewer makes the log look like a complete,
trustworthy record, so the boundaries are stated next to it:

* **not complete**: it records actions that change something or authenticate
  someone. Reads (reports, lists, the log itself) are not recorded, and
  neither are requests a station's agent makes after it is disabled — 002
  accepted that to avoid roughly 1,440 rejected polls per station per day;
* **not tamper-evident**: the table is append-only by how the server code
  uses it, not by the database. No trigger or permission stops an account with
  write access to PostgreSQL from changing or deleting rows (checked: the
  initial migration only creates the table);
* **actor is not always authenticated**: for a rejected registration the
  actor is the hostname sent by the caller, who at that point has proven
  nothing.

These go into `docs/{ru,en}/architecture.md` and `usage.md`, and into Section
V of the constitution as a **PATCH amendment (1.0.3)**, the way 1.0.2 added the
report-scope boundaries, so "Полный список — раздел V" stays true.

**Violations:** none. The constitution edit is a Section VII amendment adding
boundaries, not a waiver of a principle.

## 4. Affected modules

| Module | Change |
|---|---|
| `server/src/warden_server/models/audit.py` | `Index("ix_audit_log_occurred_at", "occurred_at")` in `__table_args__` |
| `server/alembic/versions/` | New revision (down-revision `ee7eb82ccbe5`): `create_index` / `drop_index` |
| `server/src/warden_server/schemas/timerange.py` (new) | `TimeRange`: `start`, `end`, UTC normalization, range check |
| `server/src/warden_server/schemas/report.py` | `ReportFilter` inherits `TimeRange`; its own validators removed; behavior unchanged |
| `server/src/warden_server/schemas/audit.py` (new) | `AuditFilter`, `AuditEntryOut` |
| `server/src/warden_server/api/audit.py` (new), `main.py` | `GET /api/v1/audit`; router registration |
| `server/tests/` | Unit and integration tests (§8) |
| `agent/` | **No change.** Suite run unchanged as a regression check |
| `web/src/api/{client,types}.ts` | `listAudit`, `AuditFilters`; `AuditEntry` |
| `web/src/lib/audit.ts` (new) | Labels, groups, `detail` and party formatting |
| `web/src/components/RangeFilter.tsx` (new), `icons.tsx`, `AppShell.tsx` | Shared range control; a log icon; the sidebar item |
| `web/src/pages/AuditPage.tsx` (new), `ReportsPage.tsx` | The screen; `ReportsPage` switches to `RangeFilter` |
| `web/src/App.tsx`, `web/src/styles.css` | `/audit` route; only existing tokens |
| `web/tests/unit/` | Tests for the client call, `lib/audit.ts`, the page, the nav |
| `contracts/openapi.yaml` | One new path, two new schemas |
| `docs/ru/`, `docs/en/` | Architecture (audit log section and boundaries), usage (the screen, honest status) |
| `.specify/memory/constitution.md` | 1.0.2 → 1.0.3, two Section V bullets, version-history row |

## 5. Data formats

**Database:** no new tables or columns. One new index, `ix_audit_log_occurred_at`.

**Endpoint** (operator JWT bearer):

| Endpoint | Request | Success | Errors |
|---|---|---|---|
| `GET /api/v1/audit` | query: `start`, `end`, `actor`, `action`, `limit`, `offset` | 200 `list[AuditEntryOut]` | 401; 422 (`end <= start`, bad types, `limit`/`offset` bounds, `action` outside `[a-z0-9_.]` or over 64 characters, empty `actor`) |

`AuditEntryOut` = `{id, actor, action, target, occurred_at, detail}`. `detail`
is returned exactly as stored; the existing tests already assert it never holds
a password, and this endpoint adds no field to it.

## 6. Interface

Composed from the existing tokens and components (`.card`, tables,
`.segmented`, `.btn-primary`, `.btn-secondary`, `.field-hint`); no new color
tokens.

**Журнал (`/audit`).**
* Range: the shared `RangeFilter` — «Последний час», «Последние 24 часа»,
  «Последние 7 дней», «Свой период».
* Filters: «Кто» (text input), «Действие» (select: «Все действия»; groups
  «Действия операторов», «Действия станций», «Токены регистрации», «Запросы
  окон»; then each single action), «Показать».
* Result: a table — Время (date and time with seconds, `ru-RU`), Действие
  (Russian name, raw code in the tooltip), Кто, Объект, Подробности. Long
  values wrap; nothing is truncated silently.
* States: loading; error («Не удалось загрузить журнал»); empty («За выбранный
  период записей нет.» — not an error); «Показать ещё» on a full page.
* A persistent hint under the filters, stating the boundaries in one or two
  sentences: the log records changes and sign-ins, not reads or a disabled
  station's rejected requests, and it is not protected against edits by
  someone with database access.

## 7. Risks

| Risk | Mitigation |
|---|---|
| Newest-first paging with an offset: a new entry arriving while the administrator loads page two would shift rows and repeat one | Every query has a fixed `end`. A preset's `end` is the instant it was applied, and new entries are stamped later, so they fall outside the range. The one residual case is a concurrent transaction that commits an entry stamped just before `end` after page one was read; accepted at this scale |
| Text in the log is not all trusted: for `agent.enroll_rejected` and `agent.enroll` the actor is a hostname sent by the caller, and a rejected registration needs no valid token | Rendered as React text, never as HTML, so no markup or script in it executes. Length is already bounded at 255 by the enrollment schema. A panel test renders `<img onerror>` text and asserts it appears literally |
| The panel's action names can fall behind the server: a later spec adds an action with no label | The raw code is shown (R-7, A-7), so nothing is hidden. Each later spec that adds an action adds its label in `lib/audit.ts`; this is written into their plans |
| `CREATE INDEX` on a large `audit_log` blocks writes on PostgreSQL | Accepted at this project's scale, as for `events` in 002; upgrade and downgrade are exercised on SQLite and real PostgreSQL |
| Deep `offset` pages get slower on a very large range | Bounded by the `limit` cap and the new index; keyset paging rejected in §2 |
| The log reads as complete and tamper-proof, and is neither | Boundaries stated on screen, in the docs, and in Section V (PATCH 1.0.3); tests assert the on-screen note renders |
| Any operator can read the whole log, including other operators' failed-login details | Today every operator is a full administrator (spec §5); the router-level dependency is the single place to narrow when roles land |
| Extracting `RangeFilter` alters the working reports screen | The extraction is its own step; `reportsPage.test.tsx` runs unchanged before and after |
| The `TimeRange` refactor changes the `/events` contract by accident | `test_openapi_contract.py` compares the checked-in file to `app.openapi()`; `test_report_filter.py` runs unchanged |

## 8. Verification plan

Nothing here touches a platform collector, so there is no live-device check to
defer (principle 7 / Section VI concerns collectors).

```bash
# server — in-memory SQLite, no hardware, no network
cd server && ruff check . && ruff format --check . && mypy src alembic \
  && bandit -c pyproject.toml -r src \
  && pytest --cov=warden_server --cov-report=xml --cov-fail-under=80
diff-cover coverage.xml --compare-branch=main --fail-under=80   # changed code, Section VI

# agent — unchanged source; regression only
cd agent && ruff check . && ruff format --check . && mypy src \
  && bandit -c pyproject.toml -r src && pytest

# panel
cd web && npm run lint && npm run format && npm test && npm run build

# migration, both directions, on SQLite and on real PostgreSQL
cd server && alembic upgrade head && alembic downgrade -1 && alembic upgrade head
```

**Acceptance criteria → tests**

| Criterion | Test |
|---|---|
| A-1 last hour, newest first, fields present | server integration: log in through the API, request the last hour; the `operator.login` entry is present with actor, action, target, time; two seeded entries at known instants come back newest first |
| A-2 end before start | server unit (`AuditFilter`, and `TimeRange` through both filters) and integration (422); panel range helper test already exists, plus a page test that no request is sent |
| A-3 actor filter | server integration: two actors, filter to one; an actor value of `%` matches nothing (exact match, not a pattern) |
| A-4 action group | server integration: `operator` returns `operator.login` and `operator.login_failed` but not `agent.disabled`; `operator.login` alone excludes `operator.login_failed`; a partial code such as `operator.log` returns nothing; `%` is rejected with 422 |
| A-5 paging | server integration: entries sharing one timestamp page through `limit`/`offset` with no loss or repeat; an entry exactly at `start` is included and one at `end` excluded |
| A-6 authentication | server integration: no token → 401 |
| A-7 unknown action | server integration: an entry with an invented action is returned verbatim; panel unit and page tests show the raw code |
| R-8 large ranges are not a window | server integration: a 30-day range returns 200 (principle 3 independence) |
| Reads are not audited | server integration: `audit_log` row count is identical before and after a `GET` |
| Index | server integration: `ix_audit_log_occurred_at` is declared on the table metadata; migration round-trip |
| Contract | `test_openapi_contract.py` equality; `/events` unchanged by the base-class refactor |
| Panel | `vitest`: default request is the last 24 hours; each preset sends its `start`/`end`; an invalid custom range sends nothing and shows the error; the actor and action controls send `actor` and `action`; a group choice sends the bare group; rows show the Russian name, actor, target, details; a station id shows the hostname and falls back to the raw id when the station list fails; markup-looking text renders literally; empty state; error state; «Показать ещё» fetches the next offset; the boundary hint is always visible; the sidebar link to `/audit` is active on its route |

**Checked only in CI or manually, and how far:** once by hand against the real
`docker compose` stack (Caddy + PostgreSQL), with the proxy on 8443/8080
because the development machine's `gitlab` container holds ports 80/443:
generate entries (a failed login, a good login, a station disabled and
re-enabled, an enrollment token), then read them in the panel — range, actor,
group and single-action filters, and paging. What this does **not** verify:
behavior on a very large log, and the screen's look in browsers beyond the one
used for the pass. Both are stated in `docs/{ru,en}/usage.md` in the same
honest terms as the existing status section.

## 9. Deviations found during implementation

* Two panel helpers beyond the plan, both in `web/src/lib/reportRange.ts`: a
  `Preset` type (the range control's choice), and `resolveRange`, which turns
  the form state (preset or custom fields) into a range or a validation
  message. Without it the "preset, or validated custom range" branch would
  have been copied into `AuditPage`; `ReportsPage` now uses it too, guarded by
  its unchanged tests.
* `RangeFilter` keeps its preset list private instead of exporting it: a
  non-component export from a component file breaks the fast-refresh lint rule
  that `categories.ts` was created to avoid in 002.
* The unit test for `AuditFilter` first listed `_` among rejected action
  characters. Codes contain underscores (`operator.login_failed`), so the
  alphabet allows it and the query escapes it instead (`autoescape=True`); an
  integration test (`a_c` must not reach `abc.*`) pins that. The rejected list
  now has `%`, spaces, uppercase, a newline, and over-long values.
* Every known action name is also an option of the action filter, so a page
  test looking a name up on the whole screen finds the `<option>` first; the
  row lookup is scoped to the table.
* `diff-cover` was run on the working tree, where the new files are still
  untracked and therefore not counted (it reported the three modified files at
  100%). Coverage was read per file instead: every new or changed server file
  is at 100% (`api/audit.py`, `schemas/audit.py`, `schemas/timerange.py`,
  `models/audit.py`, `schemas/report.py`). Re-run `diff-cover` once the change
  is committed.
* The manual pass used a compose override file kept outside the repository and
  a separate project (`warden003`) with the proxy on 18443/18080, rather than
  editing `docker-compose.yml`: host port 8080 belongs to another project's
  container. Nothing tracked was changed, and the project, its volumes, and its
  images were removed afterwards.
* **Found, not fixed (outside this spec):** `agent.inventory_change` audit rows
  carry `change_id: "None"`. `submit_inventory` writes `str(change.id)` before
  the row is flushed, and the id is a Python-side default assigned only on
  flush. The viewer shows what is stored; the defect predates this feature and
  is in a write path this spec does not touch.
* **Dropped:** the T-30 search for the project's retired transliterated name.
  The phrase was carried over from 002's checklist and the name is recorded
  nowhere in the repository; the decision is that the project keeps the name
  Warden, so the check has no subject.
