# Tasks: Audit log viewer

**Plan:** [./plan.md](./plan.md) · **Status:** done · **Date:** 2026-09-24

> Each task is a verifiable outcome (a test, an endpoint, a screen), not an
> abstract action. Check it off with `[x]` once done.
>
> Within every slice the tests come first and are seen to fail (red) before
> the implementation that makes them pass (green). The API contract is
> regenerated at the end of the server slice so the suite stays green at
> every commit — `test_openapi_contract.py` compares the checked-in file to
> `app.openapi()` and would otherwise fail as soon as the endpoint lands.
> Regenerate with `python scripts/export_openapi.py` from `server/`.

## Foundation

- [x] T-1. Create and switch to the branch `003-audit-log-viewer` (constitution Section IV); `git branch --show-current` prints it

## Slice A — server: `GET /api/v1/audit` (R-1, R-4…R-6, R-8, R-9; A-1…A-7)

- [x] T-2. Refactor guard first: run `server/tests/unit/test_schemas/test_report_filter.py` and `server/tests/integration/test_fleet_report/test_fleet_report.py`, both green, and note that `contracts/openapi.yaml` is untouched; these stay unchanged through T-5
- [x] T-3. Server unit tests, failing first, in `server/tests/unit/test_schemas/test_audit_filter.py`: a valid range is accepted with defaults (no actor, no action, `limit` 500, `offset` 0); a range of 30 days is accepted; `end` equal to or before `start` is rejected with «end must be after start»; naive timestamps are treated as UTC; one naive and one aware timestamp together do not raise `TypeError`; `limit` above 2000 and a negative `offset` are rejected; an empty `actor` is rejected; an `action` containing `%`, a space, an uppercase letter, or more than 64 characters is rejected; `operator`, `operator.login`, and `enrollment_token.create` are accepted
- [x] T-4. Server integration tests, failing first, in `server/tests/integration/test_audit_log/test_audit_log.py` (with `__init__.py`), entries inserted straight into the test database at known instants: after a real `POST /auth/login` the last-hour read contains the `operator.login` entry with actor, action, target, time and `detail` (A-1); two seeded entries come back newest first (R-4); an actor filter returns only that actor's entries and an actor of `%` returns none (A-3); `action=operator` returns `operator.login` and `operator.login_failed` but not `agent.disabled`, `action=operator.login` excludes `operator.login_failed`, `action=operator.log` returns nothing (A-4); entries sharing one timestamp page through `limit`/`offset` with no loss or repeat (A-5); an entry exactly at `start` is included and one exactly at `end` excluded; an empty range returns 200 `[]`; `end` before `start` → 422 (A-2); `action=%` → 422; a 30-day range → 200 (principle 3 independence); an entry with an invented action is returned verbatim (A-7); no token → 401 (A-6); the `audit_log` row count is identical before and after a `GET`; `ix_audit_log_occurred_at` is declared on the `audit_log` table metadata
- [x] T-5. Add `TimeRange` in new `server/src/warden_server/schemas/timerange.py` and make `ReportFilter` inherit it, deleting its own copies of the UTC and range validators; T-2's suites still pass and `contracts/openapi.yaml` is still byte-equal to `app.openapi()`
- [x] T-6. Add `Index("ix_audit_log_occurred_at", "occurred_at")` to `AuditLogEntry.__table_args__` in `server/src/warden_server/models/audit.py` and a new Alembic revision (down-revision `ee7eb82ccbe5`) with `create_index` / `drop_index`; `alembic upgrade head`, `alembic downgrade -1`, `alembic upgrade head` succeed against a fresh SQLite file
- [x] T-7. Add `AuditFilter` and `AuditEntryOut` in new `server/src/warden_server/schemas/audit.py` and `GET /api/v1/audit` in new `server/src/warden_server/api/audit.py` (router-level `require_operator`, half-open range, exact-or-dotted-group action match with `autoescape=True`, ordered by `(occurred_at DESC, id)`, bound with `Annotated[AuditFilter, Query()]`), registered in `server/src/warden_server/main.py`; T-3 and T-4 pass
- [x] T-8. Regenerate `contracts/openapi.yaml` for `/api/v1/audit` and its schemas; `test_openapi_contract.py` passes and the diff touches no `/events` line

## Slice B — panel: «Журнал» (R-1…R-8; A-2, A-7)

- [x] T-9. Guard the extraction: run `web/tests/unit/reportsPage.test.tsx` and `web/tests/unit/reportRange.test.ts`, both green; they stay unchanged through T-10
- [x] T-10. Lift the preset segmented control and the custom start/end inputs out of `web/src/pages/ReportsPage.tsx` into a controlled `web/src/components/RangeFilter.tsx` (props: the selected preset, the two custom values, and change handlers; `PRESETS` and the `Preset` type move with it) and use it from `ReportsPage`; T-9's tests still pass with no edit
- [x] T-11. Client tests, failing first, in `web/tests/unit/apiClient.test.ts`: `listAudit` sends ISO `start`/`end`, `actor`, `action`, `limit`, `offset` with the bearer token, omits `actor` and `action` when not set, and reads `/audit`; a 401 surfaces as `ApiError` with `status === 401`
- [x] T-12. Add `listAudit` and `AuditFilters` to `web/src/api/client.ts` and `AuditEntry` to `web/src/api/types.ts`; T-11 passes
- [x] T-13. Tests, failing first, in `web/tests/unit/audit.test.ts`: every one of the 17 codes the server emits today (`agent.enroll`, `agent.enroll_rejected`, `agent.inventory_change`, `agent.inventory_snapshot`, `agent.report`, `agent.report_out_of_window`, `agent.tasks_dispatched`, `agent.disabled`, `agent.enabled`, `enrollment_token.create`, `operator.login`, `operator.login_failed`, `operator.login_throttled`, `operator.password_change`, `operator.password_change_failed`, `operator.password_change_throttled`, `request.window`) has a Russian label; an unknown code returns itself; the four groups (`operator`, `agent`, `enrollment_token`, `request`) have labels; `detail` formats as `key: value` pairs, a list or object value as compact JSON, and an empty `detail` as «—»; a value equal to a known station id resolves to its hostname and any other value is returned as it is
- [x] T-14. Add `web/src/lib/audit.ts` (labels, groups, `formatDetail`, station-id resolution); T-13 passes
- [x] T-15. Tests, failing first, in `web/tests/unit/appShell.test.tsx`: the sidebar renders a link «Журнал» to `/audit`, active on its own route and not on the others
- [x] T-16. Add a log icon to `web/src/components/icons.tsx` and the «Журнал» `NavLink` to `web/src/components/AppShell.tsx`; T-15 passes
- [x] T-17. Tests, failing first, in `web/tests/unit/auditPage.test.tsx`: the default request is the last 24 hours; each preset sends its `start`/`end`; a custom range with the end before the start sends no request and shows the error; typing an actor sends `actor`; choosing a group sends the bare group and choosing a single action sends its full code; rows show the Russian action name, actor, target, and details; an unknown action shows its raw code; a station id in actor or target shows the hostname, and shows the raw id when the station list fails to load; text such as `<img src=x onerror=alert(1)>` renders literally and creates no `img` element; the empty state reads «За выбранный период записей нет.»; a failed request shows «Не удалось загрузить журнал»; «Показать ещё» appears on a full page and fetches the next offset; the hint about what the log does not record is always visible
- [x] T-18. Add `web/src/pages/AuditPage.tsx` and the `/audit` route in `web/src/App.tsx`, and any table styles in `web/src/styles.css` (existing tokens only); T-17 passes

## Documentation

- [x] T-19. Update `docs/ru/architecture.md` (canonical): a section on the audit log — what is recorded, the read endpoint and its filters, the dotted-group rule — and, under «Границы», the three limits from the plan (not complete, not tamper-evident, actor not always authenticated); the data-model table row for `audit_log` mentions the viewer
- [x] T-20. Mirror T-19 in `docs/en/architecture.md`, same headings and same statements
- [x] T-21. Update `docs/ru/usage.md`: a short «Журнал» section in «Работа в панели» (range, actor, action, paging, the on-screen hint), and the honest-status section extended with what the manual pass on the compose stack did and did not cover; remove the sentence that implies the log cannot be read from the product, if any
- [x] T-22. Mirror T-21 in `docs/en/usage.md`
- [x] T-23. Amend `.specify/memory/constitution.md` to 1.0.3 (PATCH) through the Section VII procedure: two new Section V boundaries (the audit log is not a complete record — reads and a disabled station's rejected requests are not recorded; it is append-only by server code only, so an account with database write access can alter it), a version-history row, and the updated "last amended" date; the documents made stale by it are those already covered by T-19…T-22

## Verification

- [x] T-24. Run `ruff check .`, `ruff format --check .`, `mypy src alembic`, and `bandit -c pyproject.toml -r src` in `server/` — all clean
- [x] T-25. Run the full server suite with `pytest --cov=warden_server --cov-report=xml --cov-fail-under=80` and `diff-cover coverage.xml --compare-branch=main --fail-under=80` — green, changed-code coverage at least 80%
- [x] T-26. Run `ruff check .`, `ruff format --check .`, `mypy src`, `bandit -c pyproject.toml -r src`, and `pytest` in `agent/` — all clean and green (no source change; regression run against the unchanged server contract)
- [x] T-27. Run `npm run lint`, `npm run format`, `npm test`, and `npm run build` in `web/` — all clean
- [x] T-28. Against real PostgreSQL from `docker compose` run `alembic upgrade head`, `alembic downgrade -1`, `alembic upgrade head` — the index revision applies and reverses (Docker must be started; the user's `gitlab` container holds host ports 80/443, so map the proxy to 8443/8080 for the run and restore `docker-compose.yml` to `443:443` / `80:80` afterwards)
- [x] T-29. Manual pass on the real compose stack (Caddy + PostgreSQL): log in, fail one login, create an enrollment token, disable and re-enable a station, then in the panel read the log for a preset and a custom range, filter by an actor, by the `operator` group, and by a single action, and load a second page (lower the page size temporarily or seed enough rows); record the outcome and its limits in the honest-status section of `docs/ru/usage.md` and `docs/en/usage.md`
- [x] T-30. Repository checks: no `sys.platform`/`platform.system` or platform imports in the touched server files (principle 1); `docs/ru` and `docs/en` have matching headings for the pages changed; everything added under `specs/` is English, apart from UI strings and Russian document headings quoted verbatim to identify them. The search for a retired transliterated project name, carried over from 002's checklist, was dropped: the project keeps the name Warden, so there is nothing to search for
- [x] T-31. Set **Status** to `done` in `spec.md`, `plan.md`, and this file
