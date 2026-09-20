# Implementation plan: Panel reports and settings

**Spec:** [./spec.md](./spec.md) · **Status:** done · **Date:** 2026-09-20

---

## 1. Approach

Three independent vertical slices. Each is server endpoint → contract → panel
screen, so any one can be built, tested, and reviewed on its own. **No agent
source code changes**: the agent already handles a rejected key (see A-8/A-9
below), and every new capability is operator-facing.

### Slice A — cross-station report (R-1…R-4)

A new read endpoint `GET /api/v1/events`, added to the operator-guarded
router in `api/reports.py`, next to the existing per-station daily report.

* Inputs are a Pydantic query model, `ReportFilter` (`schemas/report.py`),
  bound with `Annotated[ReportFilter, Query()]`: `start`, `end` (both
  required), `agent_id` (repeatable, optional — empty means every station),
  `category` (optional `EventCategory`), `limit`/`offset` (same bounds as the
  existing endpoints: default 500, max 2000).
* `ReportFilter.validate_range` rejects `end <= start` (A-2) and first
  normalizes both timestamps to UTC-aware, so one naive and one aware value
  cannot raise `TypeError` mid-comparison (the same hazard `EventIn` already
  guards against). FastAPI turns the failure into a normal 422.
* The query joins `events` to `agents` and returns `ReportEventOut` rows —
  `EventOut` plus `agent_id` and `hostname` (R-3). The range is half-open,
  `[start, end)`, matching the window-boundary rule in `submit_report`.
  Ordering is `(occurred_at, id)`: the `id` tie-break keeps offset pagination
  stable when several events share a timestamp.
* Unknown `agent_id` values simply match nothing (empty result, not an
  error — the spec's empty-result edge case).
* **The range is not an agent request.** It reads rows already in `events`;
  `WindowRequestIn` and `POST /agents/{id}/requests` are untouched, so the
  4-hour cap (principle 3) is neither weakened nor bypassed.
* A new Alembic revision adds `ix_events_occurred_at` on `events(occurred_at)`
  (mirrored in `Event.__table_args__`). Today `events` has no index beyond
  its keys, so a fleet-wide range query would scan the whole table.

### Slice B — settings: password and policy (R-5…R-7, R-10)

* `POST /api/v1/auth/password` (`api/auth.py`), body `PasswordChangeIn`
  (`current_password`, `new_password`), response 204.
  * `new_password` is bounded by `MIN_PASSWORD_LENGTH = 12` (a module
    constant beside `MAX_REPORT_EVENTS`, not a setting) and 1024 max (the
    same Argon2id-cost cap as `LoginRequest`); a validator rejects a new
    password equal to the current one, since A-6 requires the old one to stop
    working.
  * The handler re-verifies `current_password` with `verify_password`, stores
    `hash_password(new_password)`, and audits. A wrong current password is a
    400, deliberately not a 401 — a 401 would look like an expired session
    to the panel.
  * Failed attempts are throttled with the existing `services/throttle.py`
    under a separate key (`password-change:<username>`), so a burst of
    failures here cannot lock the operator out of login.
  * Session tokens are **not** revoked (out of scope in the spec); the
    seeded-operator bootstrap only acts on an empty `operators` table, so a
    restart never restores the old password (asserted by a test).
* `GET /api/v1/policy` (new `api/policy.py`), response `PolicyOut`. An
  explicit allow-list schema — never `Settings.model_dump()` — so a secret
  cannot be added to the response by accident. Fields, each read from the
  place that enforces it (so the display cannot drift from the behavior):
  `max_request_window_hours`, `enrollment_token_ttl_hours`,
  `session_lifetime_minutes` (`jwt_expire_minutes`), `min_password_length`,
  `max_report_events`, `max_inventory_entries`, `max_page_size`. The spec
  names window cap, token lifetime and upload limits (R-7); session lifetime
  and minimum password length are added because the password form needs the
  latter and the "sessions are not revoked" boundary is meaningless without
  the former.

### Slice C — enable/disable a station (R-8…R-10)

* `PATCH /api/v1/agents/{agent_id}` (`api/agents.py`, beside
  `create_enrollment_token`, which is already operator-facing), body
  `AgentStatusIn {status}` reusing `AgentStatus`, response `AgentOut`.
* Enforcement already exists: `require_agent` rejects any agent whose status
  is not `ACTIVE` with the same 401 it returns for a wrong key (spec's last
  edge case). This slice adds only the operator-side switch, so there is no
  second enforcement path to keep consistent.
* The change is idempotent: setting the current status returns 200 and writes
  no audit row; a real transition writes `agent.disabled` / `agent.enabled`.
* The agent needs nothing: a 401 raises `HTTPStatusError` out of
  `ServerClient._request` (4xx is not retried), and the scheduler's `_loop`
  catches it, logs it, and tries again on the next tick — so the agent keeps
  running, resumes on its own after re-enable, and the key never changes.

### Panel

Navigation becomes real (`NavLink` for `/agents`, `/reports`, `/settings`;
"Станции" stays active on `/agents/*`), replacing the inert placeholders in
`AppShell.tsx`. Two new pages, `ReportsPage` and `SettingsPage`, plus a
`disabled` variant of `StatusPill`. Details in §6.

### Spec points this plan resolves

1. **"Today" vs "last day".** The scenario text says "last hour / today / last
   week"; R-2 says "last hour, last day, last week". The plan follows R-2 and
   A-1: rolling presets (last hour, last 24 hours, last 7 days), computed from
   the moment of applying. A calendar "today" would need a timezone decision
   the spec does not make.
2. **Where disabling lives.** The primary scenario puts it on the Settings
   screen ("the same screen"), so it goes there, as a stations card. The
   station list and detail only *display* the disabled state.
3. **What the report can show.** Events reach the server only through window
   requests (principle 2). A fleet report over "the last week" therefore
   shows what was already requested and delivered, not everything stations
   did. This is a real property of the design, not a defect to hide; see
   principle 10 in §3 and the first risk in §7.

### Order of work

Slice C (smallest) → B → A (needs the migration) → panel wiring → docs and
constitution PATCH. Within each slice: server change and its tests, contract
regeneration, panel client/types, page, panel tests.

## 2. Alternatives considered

| Option | Why rejected |
|---|---|
| Put the enable/disable control on the station detail page | It would sit next to the window-request form, where a misclick disables a live station; the spec also puts it on Settings. Detail keeps read-only status display instead |
| `POST /reports/query` with a JSON body for the fleet report | This is a read. `GET` with query parameters matches the two existing report endpoints and the repeatable `agent_id` filter fits a query string; a body only helps if filters outgrow URL length, which four short filters do not |
| Remove a compromised station (`DELETE /agents/{id}`) | Events, tasks, and inventory reference `agents.id`; deleting destroys exactly the history an investigation needs, and R-9 requires that it can be reversed. A status flag does both |
| Revoke sessions on password change (a `token_version` on `operators`, checked in `require_operator`) | Real fix for the boundary in the spec's edge-case table, but it needs a schema change, a JWT claim, and its own tradeoffs — the spec places it out of scope. It stays a stated boundary (§7) |
| Make policy values editable from the panel (DB-backed settings) | Out of scope in the spec; would add a settings table, validation, and change-audit for values that are safety limits. Read-only display is what R-7 asks for |
| Keyset pagination for the fleet report | Better at deep offsets, but the panel and the existing endpoints paginate with `limit`/`offset` ("Показать ещё"); mixing schemes would fork the panel code. The `(occurred_at, id)` tie-break fixes the correctness problem offset paging actually has |
| Share the login throttle counter with password-change failures | A holder of a stolen token could then lock the real operator out of login. A separate key costs one string |

## 3. Constitution compliance

| Principle | How it is satisfied |
|---|---|
| 1. Platform code is isolated | No OS-dependent code is added. The agent is unchanged; the server files touched contain no `sys.platform`/`platform.system` and no platform imports (checked with the grep from the principle's *Check*) |
| 2. Data does not leave the buffer without a request | Unchanged agent, unchanged transport. The fleet report reads only `events` rows that arrived through a `window_request`; disabling a station pushes nothing to it (D-1) — the agent learns of it from its next poll being rejected |
| 3. Request window ≤ 4 hours | `WindowRequestIn.validate_range` and `validate_task_window` are not modified. A regression test in the fleet-report suite asserts a 5-day report range succeeds **and** a 4h+1min window request is still rejected — proving the two operations are independent |
| 4. Buffer retention is bounded | Not touched (no agent change) |
| 5. Exchange is authenticated and encrypted | All four new endpoints depend on `require_operator` (`/events` and `/policy` via the router-level dependency, `PATCH` and `POST /auth/password` per endpoint); a test per endpoint asserts 401 without a token. Disabled-station enforcement is the existing `AgentStatus.ACTIVE` check in `require_agent`. Password change re-verifies the current password (Argon2id) and stores only the new hash. `PolicyOut` is an allow-list schema; a test asserts the response contains no configured secret. TLS is unchanged (Caddy) |
| 6. Inventory is versioned | Not touched |
| 7. Logic is testable without real hardware | All server tests run on the in-memory SQLite fixtures in `tests/conftest.py`; the agent-side check uses the existing `httpx.ASGITransport` integration fixtures; web tests run in `vitest`. No device, elevated privilege, or live network |
| 8. Every action is logged | `log_event` at every mutating endpoint: `operator.password_change`, `operator.password_change_failed` (reason only, never a password), `operator.password_change_throttled`, `agent.disabled`, `agent.enabled` (detail: hostname). Errors on these paths are audited before the exception is raised, as `login` does. **Interpretation:** the two new read endpoints are not audited, matching the existing reads (`/agents`, daily report) and the principle's own list of audited actions; see §7 |
| 9. Language mode | Docstrings/comments English; `detail` strings from the server stay English, as today, and the panel maps them to Russian (as `LoginPage` does); all UI copy Russian; `docs/ru` canonical with `docs/en` kept in sync in the same change |
| 10. Honesty about boundaries | (a) The Reports screen carries a persistent note that it shows only events delivered through window requests; (b) the Settings password card states that already-issued sessions stay valid for `session_lifetime_minutes`; (c) `docs/ru/usage.md`'s advice to change the seeded password, which today the product cannot honor, now points at the feature; (d) `docs/{ru,en}/architecture.md` "Границы/Boundaries" gains the report-scope, duplicate-events, and session-lifetime limits; (e) a **PATCH constitution amendment (1.0.2)** adds the two boundaries to Section V, the same way 1.0.1 added one, so "Полный список — раздел V" stays true |
| 11. API contract is the single source of truth | `contracts/openapi.yaml` is regenerated from `app.openapi()` in the same change as each endpoint; the existing byte-equality test (`test_openapi_contract.py`) fails on drift. The CI `schemathesis` job runs without an operator token, so for these authenticated paths it only exercises pre-authentication behavior; the equality test is the real guard |

**Violations:** none. The only constitution edit is the Section V PATCH
above, made through the Section VII procedure, not a waiver of a principle.

## 4. Affected modules

| Module | Change |
|---|---|
| `server/src/warden_server/models/event.py` | `Index("ix_events_occurred_at", "occurred_at")` in `__table_args__` |
| `server/alembic/versions/` | New revision (down-revision `59fb180e4891`): `create_index` / `drop_index` |
| `server/src/warden_server/schemas/report.py` (new) | `ReportFilter`, `ReportEventOut` |
| `server/src/warden_server/schemas/auth.py` | `MIN_PASSWORD_LENGTH`, `PasswordChangeIn` |
| `server/src/warden_server/schemas/agent.py` | `AgentStatusIn` |
| `server/src/warden_server/schemas/policy.py` (new) | `PolicyOut` |
| `server/src/warden_server/api/reports.py` | `GET /api/v1/events` |
| `server/src/warden_server/api/auth.py` | `POST /api/v1/auth/password` |
| `server/src/warden_server/api/agents.py` | `PATCH /api/v1/agents/{agent_id}` |
| `server/src/warden_server/api/policy.py` (new), `main.py` | `GET /api/v1/policy`; router registration |
| `server/tests/` | Unit and integration tests (§8) |
| `agent/` | **No source change.** One new integration test in `tests/integration/test_full_cycle/` |
| `web/src/api/{client,types}.ts` | `getFleetEvents`, `getPolicy`, `changePassword`, `setAgentStatus`; `FleetEvent`, `Policy` |
| `web/src/lib/` | `reportRange.ts` (presets, range check), `passwordValidation.ts` |
| `web/src/pages/` | `ReportsPage.tsx`, `SettingsPage.tsx` (new); `AgentsPage.tsx` (disabled state) |
| `web/src/components/` | `AppShell.tsx` (real navigation), `StatusPill.tsx` (`disabled`), `EventList.tsx` (`showStation`, `emptyMessage`) |
| `web/src/App.tsx`, `web/src/styles.css` | Two routes; `.btn-secondary`, `.btn-danger`, segmented control — existing tokens only |
| `web/tests/unit/` | Tests for the range helpers, both pages, the new client calls |
| `contracts/openapi.yaml` | Four new paths, four new schemas |
| `docs/ru/`, `docs/en/`, `README.md` | Architecture (authentication, boundaries), usage (password, stations, reports); README coverage table wording for reports |
| `.specify/memory/constitution.md` | 1.0.1 → 1.0.2, two Section V bullets, version-history row |

## 5. Data formats

**Database:** no new tables or columns. One new index, `ix_events_occurred_at`.
Audit rows reuse `audit_log(actor, action, target, detail)`.

**Endpoints** (all operator-authenticated, JWT bearer):

| Endpoint | Request | Success | Errors |
|---|---|---|---|
| `GET /api/v1/events` | query: `start`, `end`, `agent_id`×n, `category`, `limit`, `offset` | 200 `list[ReportEventOut]` | 401; 422 (`end <= start`, bad types, `limit`/`offset` bounds) |
| `PATCH /api/v1/agents/{agent_id}` | `{"status": "active" \| "disabled"}` | 200 `AgentOut` | 401; 404 unknown agent; 422 |
| `POST /api/v1/auth/password` | `{"current_password", "new_password"}` | 204 | 400 wrong current password; 401; 422 (too short, too long, equals current); 429 throttled |
| `GET /api/v1/policy` | — | 200 `PolicyOut` | 401 |

`ReportEventOut` = `{id, category, occurred_at, payload, agent_id, hostname}`;
`hostname` is the station's *current* name (`agents.hostname` is not
versioned). `PolicyOut` fields are listed in Slice B. Both land in
`contracts/openapi.yaml`, generated from the running app and guarded by the
equality test.

## 6. Interface

No design canvas exists for these two screens; they are composed from the
approved canvas's tokens and components (`.card`, tables, `.pill`,
`.cat-tag`, `.btn-primary`, `.field-hint`). Only two button variants and a
segmented control are added to `styles.css`, without new color tokens.

**Navigation.** "Станции", "Отчёты", "Настройки" are links; the placeholder
comment and non-interactive `div`s in `AppShell.tsx` go away.

**Reports (`/reports`).**
* Range: segmented control — «Последний час», «Последние 24 часа»,
  «Последние 7 дней», «Свой период» (reveals two `datetime-local` inputs).
  Default is 24 hours: because reports show only requested data (§7), a
  one-hour default would often be empty. Presets are computed when the user
  applies them, not when the page loads.
* Filters: stations as a checkbox list (nothing checked = all), category as a
  select («Все категории»), «Показать» button. Client check for end ≤ start
  mirrors, does not replace, the server's.
* Result: a table — Время (date and time, since ranges span days), Станция
  (hostname, linking to the station), Категория, Событие — reusing
  `EventList` with `showStation`; «Показать ещё» when a page comes back full,
  as on the station screen.
* States: loading; error («Не удалось загрузить отчёт»); empty («За выбранный
  период данных нет.» — not an error).
* A persistent hint under the filters: «Показаны только события, которые
  станции передали по запросам окна. Активность вне запрошенных окон здесь не
  видна.»

**Settings (`/settings`), three cards.**
1. *Смена пароля* — current, new, repeat. Client checks (minimum length taken
   from the policy response, match, differs from current) run before the
   request. Server 400/422/429 map to Russian messages. On success: «Пароль
   изменён. Уже выданные сессии остаются действительными до истечения срока
   (N ч).»
2. *Политика сервера* — read-only definition list with units, and a line that
   values change only through server configuration.
3. *Станции* — table with hostname, OS, status pill, and a «Отключить» /
   «Включить» button. Disabling asks for an inline confirmation naming the
   station; enabling does not. The row updates from the `PATCH` response.

**Status display.** `StatusPill` gains `disabled` («отключена», warning
tokens). The station list shows it regardless of `last_seen_at` and excludes
disabled stations from the "в сети" count.

## 7. Risks

| Risk | Mitigation |
|---|---|
| The report looks like "everything the fleet did" but shows only delivered window data (principle 2) | Persistent on-screen note; boundary in the docs and Section V (PATCH 1.0.2); tests assert the note renders |
| Overlapping or repeated window requests store the same event twice (there is no ingestion dedup), so a week-long report can show duplicates. The existing daily report has the same property | Not changed here — dedup touches ingestion and the existing endpoint, outside the spec. Stated in the docs; proposed as a separate spec |
| A password change does not revoke sessions: a stolen token stays usable until it expires (8 h by default) | Out of scope per the spec; stated on the Settings card and in the docs, with the lifetime shown from the server's real value. Follow-up: session revocation |
| A stolen token turns the password endpoint into an oracle for the current password | Failures throttled per username (5 per 5 min, the login limits), audited, Argon2id-cost input caps. The throttle is in-process — the same documented limitation as login |
| A disabled agent keeps polling each minute and logs a 401 stack trace on its workstation each tick; the server does not audit these rejections | Accepted: auditing each rejected poll would write about 1,440 rows per station per day. Documented; a 401 back-off in the agent is a possible follow-up, not needed for R-8/R-9 |
| A window request can still be placed for a disabled station (the existing endpoint does not check status); it stays pending and is answered after re-enable, mostly from an already-pruned buffer | Existing behavior is declared unchanged by the spec. Documented; a 409 on disabled stations is a possible follow-up |
| `CREATE INDEX` on a large `events` table blocks writes on PostgreSQL | Accepted at this project's scale; the revision is a plain `create_index`. Upgrade and downgrade are exercised on SQLite and real PostgreSQL |
| Deep `offset` pages get slower on a very large range | Bounded by the `limit` cap and the new index; keyset paging rejected in §2 |
| The new endpoints are not audited on read, while principle 8 speaks of accountability for "who requested what" | Interpretation kept consistent with all existing reads. If read-auditing is wanted, it is a separate spec that also covers the existing daily report; raised in the handover, not decided silently |
| The two new screens were not reviewed as a design | Built from the canvas's own tokens; the user reviews them running. Extending the canvas first is optional and available |

## 8. Verification plan

Nothing here touches a platform collector, so there is no live-device check
to defer (principle 7 / Section VI concerns collectors); the boundaries below
say what *is* and is *not* verified where.

```bash
# server — in-memory SQLite, no hardware, no network
cd server && ruff check . && ruff format --check . && mypy src alembic \
  && bandit -c pyproject.toml -r src \
  && pytest --cov=warden_server --cov-report=xml --cov-fail-under=80
diff-cover coverage.xml --compare-branch=main --fail-under=80   # changed code, Section VI

# agent — unchanged source; the new cross-package integration test
cd agent && ruff check . && ruff format --check . && mypy src \
  && bandit -c pyproject.toml -r src && pytest tests/integration

# panel
cd web && npm run lint && npm run format && npm test && npm run build

# migration, both directions, on SQLite and on real PostgreSQL
cd server && alembic upgrade head && alembic downgrade -1 && alembic upgrade head
```

**Acceptance criteria → tests**

| Criterion | Test |
|---|---|
| A-1 fleet report, no station filter, rows carry station | server integration: events for two stations; response lists both, each with `hostname`/`agent_id` |
| A-2 end before start | server unit (`ReportFilter`) and integration (422); panel range helper unit test |
| A-3 two-station filter | server integration: three stations, filter to two, third absent |
| R-4 category filter; empty result; pagination | server integration: category narrows; empty range → 200 `[]`; equal-timestamp rows page without loss or repeat |
| Naive/aware timestamps | server unit: mixed naive and aware inputs normalize, no `TypeError` |
| Principle 3 independence | server integration: 5-day report range → 200 while a 4h+1min window request → 422 |
| A-4 wrong current password | server integration: 400, hash unchanged, `operator.password_change_failed` audited |
| A-5 too-short password | server unit + integration: 422, nothing stored |
| A-6 change then log in | server integration: new password logs in, old returns 401; **restart-safety:** `ensure_seed_operator` after the change does not restore the old hash |
| Throttle / secrets | server integration: sixth bad attempt → 429 and `operator.password_change_throttled`; audit detail contains no password string |
| A-7 policy | server integration: values equal the enforcing constants/settings; 401 without token; response body contains neither `jwt_secret` nor seed credentials. Panel test: values render read-only |
| A-8 disable | server integration: after `PATCH disabled`, agent `GET /tasks`, `POST /reports`, `POST /inventory` return the same 401 as a wrong key. **Agent integration test:** the real `ServerClient` against the real app raises `HTTPStatusError`, and `run_poll_pass` recovers on the next call after re-enable |
| A-9 re-enable | same tests: the same agent key authenticates again |
| A-10 audit | server integration: `agent.disabled`, `agent.enabled`, `operator.password_change` rows exist; a no-op `PATCH` adds none |
| 401 without token, 404 unknown agent | server integration, one case per new endpoint |
| Panel behavior | `vitest`: preset → expected `start`/`end` in the request; station column and empty state render; persistent scope note; password mismatch/short blocked client-side; disable requires the inline confirmation then calls `PATCH`; disabled pill and count |
| Contract | `test_openapi_contract.py` (equality) locally and in CI; the unauthenticated `schemathesis` job adds only a no-5xx check on the new paths |

**Checked only in CI or manually, and how far:** the panel and server are
additionally exercised once by hand against the real `docker compose` stack
(Caddy + PostgreSQL) — log in, change the password, place windows, view the
fleet report, disable and re-enable a station via the API. What this does
**not** verify: behavior of a real workstation agent on Linux or Windows when
disabled (covered only by the in-process integration test with the real
server app), and the two new screens' look in a real browser beyond what is
checked during that manual pass. Both are stated in `docs/ru/usage.md` in the
same honest terms as the collector-verification section.

## 9. Deviations found during implementation

* `.btn-secondary` already existed (from the enrollment-token flow committed
  after this plan's baseline), so only `.btn-danger` was added to `styles.css`.
* Two panel helpers beyond the plan: `web/src/lib/stationStatus.ts` (status
  derivation shared by the station list and the settings page) and
  `web/src/lib/categories.ts` (category labels shared by the tag and the report
  filter; kept out of the component file so the fast-refresh lint rule holds).
* `DEFAULT_PAGE_SIZE` / `MAX_PAGE_SIZE` moved into `schemas/report.py`, and
  `api/reports.py` imports them: a schema module cannot import from `api`.
* A `MAX_PASSWORD_LENGTH` constant (1024) now backs both `LoginRequest` and
  `PasswordChangeIn`; the login limit itself is unchanged.
* Inactive sidebar links use `--text-secondary` rather than `--text-tertiary`:
  they are interactive now, and the dimmer tone had marked them as inert.
* The manual pass ran in a separate compose project with fresh volumes and the
  proxy on 8443/8080, because host ports 80/443 belong to an unrelated
  container on the development machine.
