# Tasks: Panel reports and settings

**Plan:** [./plan.md](./plan.md) · **Status:** done · **Date:** 2026-09-20

> Each task is a verifiable outcome (a test, an endpoint, a screen), not an
> abstract action. Check it off with `[x]` once done.
>
> Within every slice the tests come first and are seen to fail (red) before
> the implementation that makes them pass (green). The API contract is
> regenerated at the end of each server slice so the suite stays green at
> every commit — `test_openapi_contract.py` compares the checked-in file to
> `app.openapi()` and would otherwise fail as soon as an endpoint lands.
> Regenerate with `python scripts/export_openapi.py` from `server/`.

## Foundation

- [x] T-1. Create and switch to the branch `002-panel-reports-and-settings` (constitution Section IV); `git branch --show-current` prints it

## Slice C — enable/disable a station (R-8, R-9, R-10; A-8, A-9, A-10)

- [x] T-2. Server integration tests, failing first, in `server/tests/integration/test_agent_status/test_agent_status.py`: `PATCH /api/v1/agents/{id}` with `disabled` returns 200 and an `AgentOut` with `status: disabled`; a disabled agent's `GET /tasks`, `POST /reports`, and `POST /inventory` each return the same 401 as a wrong key; re-enabling makes the same key work again; `agent.disabled` / `agent.enabled` audit rows exist with the hostname in `detail`; a `PATCH` to the current status returns 200 and adds no audit row; unknown agent → 404; no operator token → 401; an invalid status value → 422
- [x] T-3. Agent integration test, failing first, in `agent/tests/integration/test_full_cycle/test_disabled_agent.py`: with the real `ServerClient` against the real server app, disabling the agent through the operator API makes `run_poll_pass` raise `httpx.HTTPStatusError` (401) without retrying; after re-enabling, the next `run_poll_pass` with the same key succeeds
- [x] T-4. Add `AgentStatusIn` to `server/src/warden_server/schemas/agent.py` and `PATCH /api/v1/agents/{agent_id}` to `server/src/warden_server/api/agents.py` (operator-only, idempotent, audits only a real transition); T-2 and T-3 pass
- [x] T-5. Regenerate `contracts/openapi.yaml` for the new path and schema; `test_openapi_contract.py` passes

## Slice B — settings: password and policy (R-5, R-6, R-7, R-10; A-4…A-7)

- [x] T-6. Server unit tests, failing first, in `server/tests/unit/test_schemas/test_password_change.py`: a new password of 11 characters is rejected and 12 accepted; longer than 1024 rejected; a new password equal to the current one rejected
- [x] T-7. Server integration tests, failing first, in `server/tests/integration/test_password_change/test_password_change.py`: wrong current password → 400, hash unchanged, `operator.password_change_failed` audited; too-short new password → 422, nothing stored; success → 204, the new password logs in and the old one returns 401; `ensure_seed_operator` run after the change does not restore the old hash; sixth failed attempt → 429 and `operator.password_change_throttled`; after five failed password changes a correct login still succeeds (separate throttle key); no operator token → 401; audit `detail` never contains either password string
- [x] T-8. Add `MIN_PASSWORD_LENGTH = 12` and `PasswordChangeIn` to `server/src/warden_server/schemas/auth.py` and `POST /api/v1/auth/password` to `server/src/warden_server/api/auth.py` (Argon2id re-verification, per-username throttle under the key `password-change:<username>`, audit on success, failure, and throttle); T-6 and T-7 pass
- [x] T-9. Server integration tests, failing first, in `server/tests/integration/test_policy/test_policy.py`: `GET /api/v1/policy` without a token → 401; each returned value equals the setting or constant that enforces it (`max_request_window_hours`, `enrollment_token_ttl_hours`, `jwt_expire_minutes`, `MIN_PASSWORD_LENGTH`, `MAX_REPORT_EVENTS`, `MAX_INVENTORY_ENTRIES`, `MAX_PAGE_SIZE`); the response keys equal an explicit allow-list and its text contains neither the configured `jwt_secret` nor the database URL
- [x] T-10. Add `PolicyOut` in `server/src/warden_server/schemas/policy.py`, `GET /api/v1/policy` in the new `server/src/warden_server/api/policy.py`, and register the router in `main.py`; T-9 passes
- [x] T-11. Regenerate `contracts/openapi.yaml` for the password and policy paths and schemas; `test_openapi_contract.py` passes

## Slice A — cross-station report (R-1…R-4; A-1…A-3)

- [x] T-12. Server unit tests, failing first, in `server/tests/unit/test_schemas/test_report_filter.py`: `end` equal to or before `start` is rejected; naive timestamps are treated as UTC; one naive and one aware timestamp together do not raise `TypeError`; `limit` above 2000 and a negative `offset` are rejected
- [x] T-13. Server integration tests, failing first, in `server/tests/integration/test_fleet_report/test_fleet_report.py`: events from two stations come back in one response, each row with `agent_id` and `hostname` (A-1); a filter on two of three stations excludes the third (A-3); the category filter narrows the result; an empty range returns 200 `[]`; an unknown `agent_id` returns `[]`; an event exactly at `start` is included and one exactly at `end` excluded; rows sharing one timestamp page through `limit`/`offset` with no loss or repeat; no token → 401; a 5-day range returns 200 while a 4h+1min window request is still rejected with 422 (principle 3 independence). Also assert that `ix_events_occurred_at` is declared on the `events` table metadata
- [x] T-14. Add `Index("ix_events_occurred_at", "occurred_at")` to `Event.__table_args__` in `server/src/warden_server/models/event.py` and a new Alembic revision (down-revision `59fb180e4891`) with `create_index` / `drop_index`; `alembic upgrade head`, `alembic downgrade -1`, `alembic upgrade head` succeed against a fresh SQLite file
- [x] T-15. Add `ReportFilter` and `ReportEventOut` in `server/src/warden_server/schemas/report.py` and `GET /api/v1/events` to `server/src/warden_server/api/reports.py` (join to `agents`, half-open range, ordered by `(occurred_at, id)`, bound with `Annotated[ReportFilter, Query()]`); T-12 and T-13 pass
- [x] T-16. Regenerate `contracts/openapi.yaml` for `/api/v1/events` and its schemas; `test_openapi_contract.py` passes

## Panel

- [x] T-17. Client tests, failing first, in `web/tests/unit/apiClient.test.ts`: `getFleetEvents` sends ISO `start`/`end`, repeated `agent_id`, `category`, `limit`, `offset` with the bearer token; `getPolicy` reads `/policy`; `changePassword` posts both fields and resolves on 204; `setAgentStatus` sends `PATCH` with `{status}`; a 400 surfaces as `ApiError` with `status === 400`
- [x] T-18. Add `getFleetEvents`, `getPolicy`, `changePassword`, `setAgentStatus` to `web/src/api/client.ts` and `FleetEvent`, `Policy` to `web/src/api/types.ts`; T-17 passes
- [x] T-19. Add `web/src/lib/reportRange.ts` (preset → `start`/`end` from a given `now`, and end-after-start check) with `web/tests/unit/reportRange.test.ts` written first: last hour, last 24 hours, last 7 days from a fixed instant; an end not after the start returns the Russian error text
- [x] T-20. Add `web/src/lib/passwordValidation.ts` (minimum length from the policy, repeat must match, new must differ from current) with `web/tests/unit/passwordValidation.test.ts` written first
- [x] T-21. Extend `web/tests/unit/agentsPage.test.tsx`, failing first: a disabled station shows «отключена» regardless of `last_seen_at` and is excluded from the «в сети» count
- [x] T-22. Add the `disabled` variant (warning tokens) to `web/src/components/StatusPill.tsx` and use it in `web/src/pages/AgentsPage.tsx`; T-21 passes
- [x] T-23. Tests, failing first, in `web/tests/unit/appShell.test.tsx`: the sidebar renders links to `/agents`, `/reports`, `/settings`; «Станции» is active on `/agents/<id>`; «Отчёты» and «Настройки» are active on their own routes
- [x] T-24. Replace the inert placeholders in `web/src/components/AppShell.tsx` with `NavLink`s; T-23 passes
- [x] T-25. Tests, failing first, in `web/tests/unit/reportsPage.test.tsx`: the default request is the last 24 hours; choosing each preset sends the matching `start`/`end`; a custom range with the end before the start sends no request and shows the error; ticking stations sends one `agent_id` each; the category select sends `category`; rows show the station hostname; the empty state reads «За выбранный период данных нет.»; the scope note about window-delivered events is always visible; «Показать ещё» appears on a full page and fetches the next offset; a failed request shows «Не удалось загрузить отчёт»
- [x] T-26. Add `web/src/pages/ReportsPage.tsx`, the `/reports` route in `web/src/App.tsx`, `showStation` and `emptyMessage` props on `web/src/components/EventList.tsx`, and the segmented-control styles in `web/src/styles.css` (existing tokens only); T-25 passes
- [x] T-27. Tests, failing first, in `web/tests/unit/settingsPage.test.tsx`: policy values render read-only with units; a mismatched, too-short, or unchanged new password sends no request; a server 400 shows the wrong-current-password message and a 429 the too-many-attempts message; success shows the message including the session lifetime in hours from the policy; disabling a station requires the inline confirmation and then calls `PATCH` with `disabled`, updating the row from the response; re-enabling needs no confirmation
- [x] T-28. Add `web/src/pages/SettingsPage.tsx` (password card, read-only policy card, stations card), the `/settings` route, and `.btn-danger` in `web/src/styles.css` (existing tokens only; `.btn-secondary` already existed from the enrollment-token flow); T-27 passes

## Documentation

- [x] T-29. Update `docs/ru/architecture.md` (canonical): the Authentication section covers `POST /api/v1/auth/password`, its separate throttle key, the new audit actions, and that sessions are not revoked; the Boundaries section states that the report shows only events delivered through window requests, that overlapping requests can store duplicates, that a disabled agent keeps polling and logging 401s, and that a window request can still be placed for a disabled station
- [x] T-30. Mirror T-29 in `docs/en/architecture.md`, same headings and same statements
- [x] T-31. Update `docs/ru/usage.md`: the advice to change the seeded password now points at Settings; add short sections on the Reports screen and on disabling and re-enabling a station; extend the honest-status section — the disabled-agent flow is verified by the in-process integration test and a manual pass on the compose stack, not on a real Linux or Windows workstation
- [x] T-32. Mirror T-31 in `docs/en/usage.md`
- [x] T-33. Update the reports row wording in the root `README.md` function table (Russian) to mention the cross-station report without overstating what it shows
- [x] T-34. Amend `.specify/memory/constitution.md` to 1.0.2 (PATCH) through the Section VII procedure: two new Section V boundaries (the report screen shows only window-delivered events; password change does not revoke issued sessions), a version-history row, and the updated "last amended" date; the documents made stale by it are those already covered by T-29…T-33

## Verification

- [x] T-35. Run `ruff check .`, `ruff format --check .`, `mypy src alembic`, and `bandit -c pyproject.toml -r src` in `server/` — all clean
- [x] T-36. Run the full server suite with `pytest --cov=warden_server --cov-report=xml --cov-fail-under=80` and `diff-cover coverage.xml --compare-branch=main --fail-under=80` — green, changed-code coverage at least 80%
- [x] T-37. Run `ruff check .`, `ruff format --check .`, `mypy src`, and `bandit -c pyproject.toml -r src` in `agent/` — all clean
- [x] T-38. Run the full agent suite (`pytest`) — green, including the new disabled-agent integration test and the existing platform-gated skips
- [x] T-39. Run `npm run lint`, `npm run format`, `npm test`, and `npm run build` in `web/` — all clean
- [x] T-40. Against real PostgreSQL from `docker compose` run `alembic upgrade head`, `alembic downgrade -1`, `alembic upgrade head` — the index revision applies and reverses (Docker must be started; the user's `gitlab` container holds host ports 80/443, so map the proxy to 8443/8080 for the run and restore `docker-compose.yml` to `443:443` / `80:80` afterwards)
- [x] T-41. Manual pass on the real compose stack (Caddy + PostgreSQL): log in, change the password and log in again with it, place window requests for two stations and deliver them, view the cross-station report with a preset and a custom range, disable and re-enable a station and confirm its key is rejected then accepted; record the outcome and its limits in the honest-status section of `docs/ru/usage.md` and `docs/en/usage.md`
- [x] T-42. Repository checks: no `sys.platform`/`platform.system` or platform imports in the touched server files (principle 1); a case-insensitive search of the repository (excluding `node_modules`, `.git`, `.venv`) for the project's retired transliterated name finds nothing; `docs/ru` and `docs/en` have matching headings for the pages changed; everything added under `specs/` is English, apart from UI strings and Russian document headings quoted verbatim to identify them
- [x] T-43. Set **Status** to `done` in `spec.md`, `plan.md`, and this file
