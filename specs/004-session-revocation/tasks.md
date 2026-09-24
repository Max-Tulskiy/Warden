# Tasks: Session revocation

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

- [x] T-1. Create and switch to the branch `004-session-revocation` from `main` (constitution Section IV); `git branch --show-current` prints it

## Slice A — server: a version on every session (R-1, R-4, R-9; A-6, A-11)

- [x] T-2. Server unit tests, failing first, in `server/tests/unit/test_security/test_jwt.py`: `create_access_token(subject, version)` and `decode_access_token` round-trip the subject and the version; a token with no `ver`, with a string, a float, or a boolean `ver`, and a garbage token all decode to `None`; two tokens for different versions carry the same `exp` for the same instant (the version does not touch the lifetime)
- [x] T-3. Server integration tests, failing first, in `server/tests/integration/test_session_revocation/test_version_check.py` (with `__init__.py`): a token from a real login works on a panel read; after the operator's `token_version` is raised in the database the same token gets 401 and a fresh login works; a token one version behind and a token one version ahead both get 401; a correctly signed token with no `ver` gets 401; a correctly signed token for an unknown username gets 401; no token → 401
- [x] T-4. Add `token_version` (integer, not null, `server_default` 0) to `server/src/warden_server/models/operator.py` and a new Alembic revision (down-revision `5b03c4109d6c`) with `add_column` / `drop_column`; `alembic upgrade head`, `alembic downgrade -1`, `alembic upgrade head` succeed against a fresh SQLite file, and an operator row present before the upgrade reads `token_version` 0 afterwards
- [x] T-5. Add `TokenClaims` and change `create_access_token` / `decode_access_token` in `server/src/warden_server/security.py`; make `require_operator` in `server/src/warden_server/api/deps.py` refuse a version mismatch with the existing 401; make `login` in `server/src/warden_server/api/auth.py` issue the operator's version; T-2 and T-3 pass and the rest of the server suite still passes

## Slice B — server: what raises the version (R-1, R-2, R-3, R-6, R-7; A-1…A-5, A-7)

- [x] T-6. Server integration tests, failing first, in `server/tests/integration/test_session_revocation/test_revocation.py`: with two logins, a successful `POST /auth/password` from the first returns 200 with an `access_token`, the second session then gets 401, the first session's old token gets 401, and the returned token works (A-1, A-2); `POST /auth/logout-all` returns 204 and then both sessions get 401, and a fresh login works (A-3, A-4); a wrong current password (400), a too-short new password (422), and a throttled attempt (429) each leave the second session working (A-5, R-7); `logout-all` with no token → 401; `operator.password_change` and `operator.sessions_revoked` audit rows exist and no audit `detail` contains either password or any token (A-7); a second `logout-all` with the token the first one just ended → 401
- [x] T-7. Update `server/tests/integration/test_password_change/test_password_change.py` where it asserted `204`: a successful change is now `200` with `access_token`; every other assertion there is unchanged and still passes
- [x] T-8. In `server/src/warden_server/api/auth.py`, raise `token_version` with a single SQL expression (`token_version + 1`) on a successful password change and in the new `POST /api/v1/auth/logout-all`; return a `TokenResponse` for the new version from the password change (`200`, refreshing the row after the commit); write `operator.sessions_revoked` for `logout-all`; T-6 and T-7 pass
- [x] T-9. Regenerate `contracts/openapi.yaml` for the changed `/api/v1/auth/password` response and the new `/api/v1/auth/logout-all`; `test_openapi_contract.py` passes

## Constitution

- [x] T-10. Amend `.specify/memory/constitution.md` to 1.1.0 (MINOR) through the Section VII procedure: a new decision D-9 recording the per-operator version counter, why it beats a token denylist, a session table, and a timestamp comparison, and what it cannot do; the Section V bullet on password change and sessions rewritten to what is still true (only all of an operator's sessions can be ended at once; a stolen session works until the version is raised, the password is changed, or it expires; a token from before the upgrade is refused once); a version-history row; the updated "last amended" date; the documents made stale by it are those covered by T-21…T-24

## Slice C — panel: stay signed in, and notice a refused session (R-2, R-5, R-8; A-8…A-10)

- [x] T-11. Client tests, failing first, in `web/tests/unit/apiClient.test.ts`: `changePassword` resolves to the `access_token` in the 200 body and still surfaces a 400 as `ApiError`; `logoutAll` sends `POST /auth/logout-all` with the bearer token and resolves on 204; with a handler set by `setUnauthorizedHandler`, a 401 to a request that carried a token calls it once and still throws `ApiError` with `status === 401`; a 401 to `login` (no token) does not call it; a 400, a 403 and a 500 do not call it; a cleared handler is not called
- [x] T-12. Add `setUnauthorizedHandler`, `logoutAll` and the new `changePassword` result to `web/src/api/client.ts`; T-11 passes
- [x] T-13. Tests, failing first, in `web/tests/unit/authProvider.test.tsx`: when the registered handler runs, the stored token and username are cleared and `sessionEnded` becomes true; two refused requests in a row leave the same state; a later `setSession` with a session sets `sessionEnded` back to false; `sessionEnded` is false on a fresh load
- [x] T-14. Add `sessionEnded` to `web/src/state/authContext.ts` and register the handler in `web/src/state/auth.tsx` (unregistering it on unmount); T-13 passes and every existing test that builds an `AuthContext` value still passes (the field is optional; see plan §9)
- [x] T-15. Tests, failing first, in `web/tests/unit/loginPage.test.tsx`: with `sessionEnded` set, the page shows «Сеанс завершён. Войдите снова.»; without it, the message is absent; a successful sign-in stores the session and navigates on
- [x] T-16. Show the message in `web/src/pages/LoginPage.tsx`; T-15 passes
- [x] T-17. Tests, failing first, in `web/tests/unit/settingsPage.test.tsx`: update the success case — the returned token is stored with `setSession` under the same username, the message reads «Пароль изменён. Остальные сеансы завершены.», and the old sentence about sessions staying valid is gone; a failed change stores nothing; the «Сеансы» card states that the current session ends too; «Завершить все сеансы» asks «Завершить все сеансы, включая этот?» first and sends nothing until «Да, завершить» is pressed; «Отмена» sends nothing; confirming calls `logout-all` and clears the session; a failed call shows an error and keeps the session
- [x] T-18. Update `web/src/pages/SettingsPage.tsx` (store the new token, the new message, the «Сеансы» card with inline confirmation); T-17 passes
- [x] T-19. Tests, failing first, in `web/tests/unit/audit.test.ts`: add `operator.sessions_revoked` to the list of emitted actions, so it needs a distinct Russian name and stays inside the `operator` group
- [x] T-20. Add the label for `operator.sessions_revoked` to `web/src/lib/audit.ts`; T-19 passes

## Documentation

- [x] T-21. Update `docs/ru/architecture.md` (canonical): the Authentication section describes the `ver` claim, `token_version`, the password change that keeps the current session and ends the others, `logout-all`, the panel's handling of a refused session, and that a pre-upgrade token is refused once; the «Границы» bullet that says a password change does not end sessions is replaced by the three limits from the constitution; the data-model table mentions `operators.token_version`
- [x] T-22. Mirror T-21 in `docs/en/architecture.md`, same headings and same statements
- [x] T-23. Update `docs/ru/usage.md`: the Settings paragraph now describes both actions and what each does to other sessions and to the current one; a note that operators sign in once after the upgrade; the honest-status section extended with what the manual pass did and did not cover
- [x] T-24. Mirror T-23 in `docs/en/usage.md`

## Verification

- [x] T-25. Run `ruff check .`, `ruff format --check .`, `mypy src alembic`, and `bandit -c pyproject.toml -r src` in `server/` — all clean
- [x] T-26. Run the full server suite with `pytest --cov=warden_server --cov-report=xml --cov-fail-under=80` and, once the change is committed, `diff-cover coverage.xml --compare-branch=main --fail-under=80` — green, changed-code coverage at least 80%
- [x] T-27. Run `ruff check .`, `ruff format --check .`, `mypy src`, `bandit -c pyproject.toml -r src`, and `pytest` in `agent/` — all clean and green (no source change; regression run)
- [x] T-28. Run `npm run lint`, `npm run format`, `npm test`, and `npm run build` in `web/` — all clean
- [x] T-29. Against real PostgreSQL from `docker compose` (a separate project with fresh volumes and the proxy on non-standard ports, without editing `docker-compose.yml`) run `alembic upgrade head`, `alembic downgrade -1`, `alembic upgrade head`, and confirm an operator row created before the upgrade reads `token_version` 0
- [x] T-30. Manual pass on that stack, through the proxy and in a real browser: two browsers signed in; a password change in one; the other refused and returned to the sign-in screen with the message; the first still signed in; «Завершить все сеансы»; a token from before the upgrade refused after it; the audit screen shows the new actions under their Russian names; record the outcome and its limits in the honest-status section of `docs/ru/usage.md` and `docs/en/usage.md`
- [x] T-31. Repository checks: no `sys.platform`/`platform.system` or platform imports in the touched server files (principle 1); `docs/ru` and `docs/en` have matching headings for the pages changed; everything added under `specs/` is English, apart from UI strings and Russian document headings quoted verbatim to identify them
- [x] T-32. Set **Status** to `done` in `spec.md`, `plan.md`, and this file
