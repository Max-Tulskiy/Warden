# Tasks: Editable operating policy

**Plan:** [./plan.md](./plan.md) · **Status:** done · **Date:** 2026-09-24

> Each task is a verifiable outcome (a test, an endpoint, a screen), not an
> abstract action. Check it off with `[x]` once done.
>
> Within every slice the tests come first and are seen to fail (red) before
> the implementation that makes them pass (green). The API contract is
> regenerated at the end of the server slices; `test_openapi_contract.py`
> compares the checked-in file to `app.openapi()` and stays red between the
> endpoint change and the regeneration, which is kept as its own commit.
> Regenerate with `python scripts/export_openapi.py` from `server/`.

## Foundation

- [x] T-1. Create and switch to the branch `006-editable-policy` from `main` (constitution Section IV); `git branch --show-current` prints it

## Slice A — storage and one place that decides (R-2, R-3, R-6, R-10; A-1…A-6, A-18)

- [x] T-2. Server unit tests, failing first, in `server/tests/unit/test_services/test_policy_service.py`: the bounds are window `1…4`, token lifetime `1…168`, session `5…1440`, and the window ceiling is 4; `configured_defaults` equals the settings, with a configured window of 6 clamped to 4; `effective_policy` with no row returns the defaults and `overridden` false, and with a row returns the saved values and `overridden` true, still clamped when the configuration says 6 and nothing is saved; `save_policy` creates the row and reports every value that changed plus `overridden` going false to true, reports only the changed value on a later save, and reports nothing for an identical save; `reset_policy` deletes the row and reports the values that differ from the defaults plus `overridden` going true to false, and reports nothing when there is no row; a first insert that fails is retried once and the save succeeds
- [x] T-3. Server unit tests, failing first, in `server/tests/unit/test_schemas/test_policy_schemas.py`: `PolicyUpdateIn` accepts each field at its minimum and its maximum and rejects one below and one above; it rejects a float, a numeric string, a boolean, a missing field, and any extra field; `WindowRequestIn` accepts a window of 2 hours when the settings say 1 (it no longer reads them) and still rejects 4 hours 1 minute
- [x] T-4. Migration test, failing first, in `server/tests/integration/test_migrations/test_policy_overrides.py`, against a temporary SQLite file: after upgrading from the previous revision the `policy_overrides` table exists and is empty; a second row with `id` 2 is refused by the singleton check; downgrading drops the table and keeps the rest; the models and migrations agree (`command.check`)
- [x] T-5. Add `WINDOW_HOURS_CEILING` and the bounds, `PolicyValues`, `PolicyBounds`, and `PolicyUpdateIn` to `server/src/warden_server/schemas/policy.py`; `server/src/warden_server/models/policy.py` (also exported from `models/__init__.py` and imported in `alembic/env.py`) and a new Alembic revision (down-revision `afddc26b2815`); `server/src/warden_server/services/policy.py`; and make `WindowRequestIn` in `schemas/task.py` check only the constant ceiling; T-2, T-3 and T-4 pass and the existing window schema tests pass unchanged
- [x] T-6. Server integration tests, failing first, in `server/tests/integration/test_policy_effect/test_uses.py` (with `__init__.py`), with the policy saved through the service: a saved window limit of 2 hours refuses a 3-hour request with 422 and accepts a 2-hour one (A-1); with nothing saved and the settings saying 6, a 5-hour request is refused (A-3); a saved token lifetime of 2 hours makes a newly issued token expire in 2 hours while a token issued before keeps its expiry (A-6); a saved session length of 30 minutes makes a new sign-in's token expire in 30 minutes, and a token issued before the change still works and keeps its expiry (A-4, A-5); a password change returns a token with the effective lifetime
- [x] T-7. Make `create_access_token` in `server/src/warden_server/security.py` take a required `lifetime`; use the effective policy in `api/requests.py`, `api/agents.py`, and `api/auth.py` (`login` and `change_password`); update `server/tests/unit/test_security/test_jwt.py` and `agent/tests/integration/conftest.py` for the new argument; T-6 passes and the rest of the server and agent suites still pass

## Slice B — endpoints (R-1, R-4…R-9; A-7…A-13)

- [x] T-8. Update `server/tests/integration/test_policy/test_policy.py` for the new `PolicyOut` (the allow-listed fields now include `overridden`, `defaults`, and `bounds`; the values equal what enforces them; still no secret), and add `test_policy_write.py`, failing first: `PUT` with three in-range values returns 200 with them in force, `overridden` true, and the defaults and bounds alongside (A-8); each of a value below its minimum, above its maximum, a float, a numeric string, a boolean, a missing field, and an extra field → 422 and nothing stored (A-2, A-7); a window of 5 hours → 422 (A-2); an identical second `PUT` → 200 and no second audit row (A-12); `policy.changed` carries `[old, new]` for each changed value and `overridden` `[false, true]` on the first save, and no password or token; `DELETE` returns the configured values and `overridden` false, audits `policy.reset` with the values it returned to (A-9, A-13), and with nothing saved does nothing and audits nothing; with the settings object changed after a save, the saved values stay in force (A-10); an observer gets 200 on `GET` and 403 on `PUT` and `DELETE` and nothing is stored (A-11); no token → 401
- [x] T-9. Add `PUT /api/v1/policy` and `DELETE /api/v1/policy` (administrator only) to the ENDPOINTS list in `server/tests/integration/test_roles/test_permission_matrix.py`, so the matrix and the documented-403 test cover them
- [x] T-10. Add `PUT` and `DELETE` and the extended `GET` to `server/src/warden_server/api/policy.py` (`require_admin` and `ADMIN_ONLY_RESPONSES` on the writes; `policy.changed` and `policy.reset` audited from what the service reports); extend `PolicyOut` in `schemas/policy.py`; T-8 and T-9 pass
- [x] T-11. Regenerate `contracts/openapi.yaml` for the new operations, the extended `PolicyOut`, and the 403s; `test_openapi_contract.py` passes

## Constitution

- [x] T-12. Amend `.specify/memory/constitution.md` to 1.3.0 (MINOR) through the Section VII procedure: a new decision D-11 (three limits in the database, edited by administrators within fixed bounds; the four-hour window ceiling is a constant; the server's configuration is the default; why one saved set rather than per-value overrides); three Section V boundaries (a change applies only to what is issued or placed afterwards; one policy for the whole deployment with the audit log as its only history; a saved policy outranks the configuration until it is reset); a version-history row; the updated "last amended" date; the documents made stale by it are those covered by T-23…T-26

## Slice C — panel (R-4, R-5, R-7, R-10…R-12; A-14…A-17)

- [x] T-13. Client tests, failing first, in `web/tests/unit/apiClient.test.ts`: `savePolicy` sends `PUT /policy` with the three values and the bearer token and resolves to the returned policy; `resetPolicy` sends `DELETE /policy` and resolves to the returned policy; a 422 and a 403 surface as `ApiError` with their status
- [x] T-14. Add `savePolicy`, `resetPolicy`, and the new `Policy` fields (`overridden`, `defaults`, `bounds`) to `web/src/api/client.ts` and `web/src/api/types.ts`; T-13 passes
- [x] T-15. Tests, failing first, in `web/tests/unit/windowRequestForm.test.tsx` and `web/tests/unit/windowValidation.test.ts` (new): `validateWindow` checks against a given number of hours and names it in its message, defaulting to four; the form shows «Промежуток не должен превышать N ч» for the limit it is given and refuses a longer window before sending
- [x] T-16. Make `web/src/lib/windowValidation.ts` and `web/src/components/WindowRequestForm.tsx` take the limit as a parameter, four by default; T-15 passes
- [x] T-17. Tests, failing first, in `web/tests/unit/agentDetailPage.test.tsx`: an administrator's page loads the policy and the form names its window limit; when the policy cannot be loaded the form falls back to four hours; an observer's page shows no form and does not fetch the policy
- [x] T-18. Load the policy in `web/src/pages/AgentDetailPage.tsx` for an administrator and pass the limit to the form; T-17 passes
- [x] T-19. Tests, failing first, in `web/tests/unit/settingsPage.test.tsx`: for an administrator the card shows three inputs with their units, ranges, and «по умолчанию» values, and «Сохранить»; a save sends all three values and shows the message about what applies when, and the card then shows the saved policy; a value out of range, empty, or not a whole number names the range and sends nothing; «Сбросить к значениям сервера» appears only when a policy is saved, asks first, and sends `DELETE` only after confirmation; a 403 shows «Недостаточно прав» and a 422 names the range; for an observer every value is a row, with no input or button; the read-only rows and the footer sentence about the configuration remain for both; adjust the existing test that asserted nothing in the card was editable
- [x] T-20. Turn the «Политика сервера» card in `web/src/pages/SettingsPage.tsx` into the editable form for an administrator, keeping read-only rows for the rest and for an observer; T-19 passes
- [x] T-21. Tests, failing first, in `web/tests/unit/audit.test.ts`: add `policy.changed` and `policy.reset` to the list of emitted actions, so each needs a distinct Russian name
- [x] T-22. Add the two names to `web/src/lib/audit.ts`; T-21 passes

## Documentation

- [x] T-23. Update `docs/ru/architecture.md` (canonical): the policy section describes what is editable and its bounds, the ceiling as a constant, that the configuration is the default and a saved policy outranks it until reset, that a change applies only from the next use, the endpoints and their audit entries, and that the window form takes the limit from the server; the «Границы» list gains the three limits; the data-model table lists `policy_overrides`
- [x] T-24. Mirror T-23 in `docs/en/architecture.md`, same headings and same statements
- [x] T-25. Update `docs/ru/usage.md`: a paragraph on editing the policy in «Настройки» (the three values, their ranges, what applies when, the reset), the note that the environment variables are now the defaults, and the honest-status section extended with what the manual pass did and did not cover
- [x] T-26. Mirror T-25 in `docs/en/usage.md`

## Verification

- [x] T-27. Run `ruff check .`, `ruff format --check .`, `mypy src alembic`, and `bandit -c pyproject.toml -r src` in `server/` — all clean
- [x] T-28. Run the full server suite with `pytest --cov=warden_server --cov-report=xml --cov-fail-under=80` and, once the change is committed, `diff-cover coverage.xml --compare-branch=main --fail-under=80` — green, changed-code coverage at least 80%
- [x] T-29. With the server installed editable (`pip install --no-deps -e server`), run `ruff check .`, `ruff format --check .`, `mypy src`, `bandit -c pyproject.toml -r src`, and `pytest` in `agent/` — all clean and green (no source change; regression run against the real server code)
- [x] T-30. Run `npm run lint`, `npm run format`, `npm test`, and `npm run build` in `web/` — all clean
- [x] T-31. Against real PostgreSQL from `docker compose` (a separate project with fresh volumes and the proxy on non-standard ports, without editing `docker-compose.yml`) run `alembic upgrade head`, `alembic downgrade -1`, `alembic upgrade head`, and confirm the table is created empty and refuses a second row
- [x] T-32. Manual pass on that stack, through the proxy and in real browsers: an administrator lowers the window and the session length; a longer window request is refused and the form names the new limit; a held session keeps its expiry while a new sign-in gets the new length; a window above four hours and out-of-range values are refused; the reset restores the configured values; changing the configuration after a save does not change what is in force; an observer sees no inputs and is refused directly; the audit screen shows both actions under Russian names; record the outcome and its limits in the honest-status section of `docs/ru/usage.md` and `docs/en/usage.md`
- [x] T-33. Repository checks: no `sys.platform`/`platform.system` or platform imports in the touched server files (principle 1); no read of the three settings outside `services/policy.py` and `config.py` (a search of `server/src`); `docs/ru` and `docs/en` have matching headings for the pages changed; everything added under `specs/` is English, apart from UI strings and Russian document headings quoted verbatim to identify them
- [x] T-34. Set **Status** to `done` in `spec.md`, `plan.md`, and this file
