# Tasks: Record who views collected data and the audit log

**Plan:** [./plan.md](./plan.md) · **Status:** draft · **Date:** 2026-09-25

> Each task is a verifiable outcome (a test, a handler, a screen), not an
> abstract action. Check it off with `[x]` once done.
>
> Tests come first and are seen to fail (red) before the implementation that
> makes them pass (green). `contracts/openapi.yaml` is regenerated right
> after the handlers whose description text changes, so the suite stays
> green at every commit. Audit rows are ordered by `occurred_at` in tests,
> never by `id` (a random UUID).

## Foundation

- [x] T-1. Work on `main`, with no branch per spec (constitution Section IV, 1.3.2); `git branch --show-current` prints `main`

## Server — record the views (R-1…R-7; A-1…A-11)

- [ ] T-2. Integration tests, failing first, in `server/tests/integration/test_read_audit/test_read_audit.py`: each of `GET /agents/{id}/events`, `GET /events`, `GET /agents/{id}/inventory/changes`, and `GET /audit` adds exactly one entry whose actor is the operator, whose action is `view.daily_report` / `view.fleet_report` / `view.inventory_changes` / `view.audit_log`, and whose target and `detail` are those of the plan's §5 table; an observer's view is recorded under the observer's name; an observer requesting `GET /audit` gets 403 and no entry; a request with no token gets 401 and no entry; an invalid parameter (for example a reversed range) gets 422 and no entry; `GET /agents`, `GET /policy`, `GET /operators`, and `GET /auth/me` add nothing; the same view twice adds two entries, and a request with `offset` above zero adds one whose `detail` carries that `offset`; a view that matches nothing returns an empty list and still adds one entry
- [ ] T-3. Tests, failing first, in the same file: with `log_event` (or the commit) made to fail, each of the four views fails and returns no data; `GET /audit?action=view` returns only view entries, `action=operator` returns none of them, and `action=view.fleet_report` returns only that code
- [ ] T-4. In `server/src/warden_server/api/reports.py`, give `daily_report`, `fleet_report`, and `inventory_changes` an `operator: Operator = Depends(require_operator)` parameter and make each call `log_event` and `db.commit()` before its query; rewrite their docstrings to say each request is recorded; T-2 passes for those three
- [ ] T-5. In `server/src/warden_server/api/audit.py`, give `audit_log` an `operator: Operator = Depends(require_admin)` parameter and make it call `log_event` and `db.commit()` before its query; replace the docstring sentence saying reading the log is not recorded; T-2 and T-3 pass
- [ ] T-6. Regenerate `contracts/openapi.yaml` (`python scripts/export_openapi.py` from `server/`) for the four changed descriptions; `test_openapi_contract.py` passes

## Panel (R-8; A-12)

- [ ] T-7. Tests, failing first, in `web/tests/unit/audit.test.ts` and `web/tests/unit/auditPage.test.tsx`: the four `view.*` codes have Russian labels; `ACTION_GROUPS` contains a `view` group labelled «Просмотры данных»; the hint under the filters no longer says reads are not recorded and says which views are recorded and which reads are not
- [ ] T-8. In `web/src/lib/audit.ts` add the four labels and the `view` group, and in `web/src/pages/AuditPage.tsx` rewrite the hint; T-7 passes

## Documentation (R-9)

- [ ] T-9. Update `docs/ru/architecture.md` (canonical): the audit log section states that views of the daily report, the cross-station report, the inventory history, and the log itself are recorded under the `view` group, written before the data is returned; the Boundaries bullet on the audit log's completeness now says which reads are recorded and that the station list, the policy, the list of operators, the session check, and rejected requests are not
- [ ] T-10. Mirror T-9 in `docs/en/architecture.md`, same section and same statements
- [ ] T-11. Update `docs/ru/usage.md`: the audit log paragraph describes the views group and that the entry for the view on screen can appear in its own result; leave the honest-status paragraph for T-19
- [ ] T-12. Mirror T-11 in `docs/en/usage.md`
- [ ] T-13. Amend `.specify/memory/constitution.md` to 1.4.0 (MINOR) through the Section VII procedure: add decision D-12 (views of collected data and of the log are recorded, before they are answered, under their own group; the station list, the policy, the list of operators, and the session check are not), rewrite the Section V boundary on unrecorded reads, add a version-history row, and update the "last amended" date; the documents made stale by it are those covered by T-9…T-12

## Verification

- [ ] T-14. Run `ruff check .`, `ruff format --check .`, `mypy src alembic`, and `bandit -c pyproject.toml -r src` in `server/` — all clean
- [ ] T-15. Run the full server suite with `pytest --cov=warden_server --cov-report=xml --cov-fail-under=80` and `diff-cover coverage.xml --compare-branch=main --fail-under=80` — green, changed-code coverage at least 80%
- [ ] T-16. Run `npm run lint`, `npm run format`, `npm test`, and `npm run build` in `web/` — all clean
- [ ] T-17. Manual pass on the real compose stack (Caddy and PostgreSQL, a throwaway project on remapped ports because the user's `gitlab` container holds 80 and 443): sign in as an administrator, create an observer, view a report and an inventory history as each, open the audit log, and confirm the entries, the `view` group filter, and the hint in a real browser
- [ ] T-18. Repository checks: no `sys.platform`/`platform.system`/platform import in the touched server files (principle 1); a case-insensitive search of the repository (excluding `node_modules`, `.git`, `.venv`) for the project's retired transliterated name finds nothing; `docs/ru` and `docs/en` have matching headings for the pages changed; everything added under `specs/008-read-audit/` is English apart from Russian UI text quoted verbatim to identify it
- [ ] T-19. Record the outcome and the limits of T-17 in the honest-status section of `docs/ru/usage.md` and `docs/en/usage.md` (a script stood in for the agents, one browser), then set **Status** to `done` in `spec.md`, `plan.md`, and this file
