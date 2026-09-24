# Implementation plan: Session revocation

**Spec:** [./spec.md](./spec.md) · **Status:** draft · **Date:** 2026-09-24

---

## 1. Approach

Three slices: the server's token check, the two operations that use it, and the
panel. **No agent source changes**: agents authenticate with their own key, and
no agent endpoint reads an operator token.

### Slice A — server: a version on every session (R-1, R-4, R-9)

* `operators` gains `token_version`, an integer, not null, default 0
  (`server_default` so the migration fills existing rows). A new Alembic
  revision (down-revision `5b03c4109d6c`) adds and drops the column.
* A session token now carries a `ver` claim next to `sub` and `exp`.
  `create_access_token(subject, version)` writes it. `decode_access_token`
  returns the claims as a small `TokenClaims` (subject, version) or `None`, and
  returns `None` for a token whose `ver` is missing or is not an integer.
* `require_operator` (`api/deps.py`) loads the operator as it does today and
  additionally refuses, with the same 401 it already uses, a token whose `ver`
  differs from the operator's `token_version`. Every operator endpoint depends
  on it, so the check reaches them all with no per-route change (R-4).
* `login` issues the token with the operator's current version.
* Equality, not "at least": a token from a version that has been bumped is
  refused, and so is one carrying a version the operator has not reached.
* Tokens issued before this change have no `ver`, so they are refused once
  after the upgrade. That is stated in the docs; nothing is lost but a sign-in.
* The expiry (`jwt_expire_minutes`) is untouched (R-9).

### Slice B — server: what bumps the version (R-1, R-2, R-3, R-6, R-7)

* `POST /api/v1/auth/password` now also ends the operator's other sessions. On
  success it raises `token_version` and returns `200` with a `TokenResponse`
  holding a token for the new version, in place of `204`. The panel uses it to
  stay signed in (R-2). The failure paths — wrong current password, throttled,
  invalid new password — are unchanged and bump nothing (R-7).
* `POST /api/v1/auth/logout-all` (operator token, no body) raises the version
  and returns `204`; the caller's own token is refused from then on (R-3). It
  writes `operator.sessions_revoked`. A password change keeps writing
  `operator.password_change` only, and the docs say it implies the revocation.
* The raise is one SQL expression, `token_version = token_version + 1`, not a
  read-modify-write in Python, so two racing requests cannot both write the
  same value and lose a revocation. After the commit the row is refreshed and
  the new token is issued from the value the database holds.
* Both endpoints stay behind `require_operator`, so an already-ended session
  cannot end anything again and gets a plain 401.
* `operator.sessions_revoked` needs a Russian name in the audit viewer's
  dictionary (`web/src/lib/audit.ts`), which 003 left as the place each later
  spec adds its own action.

### Slice C — panel: stay signed in, and notice a refused session (R-2, R-5, R-8)

* `client.ts` gets one module-level hook, `setUnauthorizedHandler`. `request()`
  calls it when a response is 401 **and** the request carried a token. A login
  with a wrong password sends no token, so it is not mistaken for an ended
  session; a wrong *current* password on the password form is already a 400 by
  design (002), for the same reason.
* `AuthProvider` registers the hook: it clears the session and sets a flag on
  the context, `sessionEnded`. `RequireAuth` then redirects to `/login` as it
  does for a missing token. `LoginPage` shows «Сеанс завершён. Войдите снова.»
  while the flag is set and clears it on the next successful sign-in. Several
  refused requests at once run the same idempotent clear, so there is no loop.
* `changePassword` now resolves to the new token. `SettingsPage` stores it with
  `setSession`, keeping the operator's name, and the success message becomes
  «Пароль изменён. Остальные сеансы завершены.»
* A new «Сеансы» card on Settings, with «Завершить все сеансы» behind an inline
  confirmation like disabling a station, states that the current session ends too.
  On success it calls `setSession(null)`, which lands on the sign-in screen (R-8).

### Spec points this plan resolves

1. **Which sessions a password change ends** — all but the one it was made on, so
   R-1 and R-2 hold together. "End all sessions" ends every session, so an
   operator who wants to sign out everywhere, including here, has one action.
2. **Where the refused-session redirect lives** — in the API client, not in each
   page, so every current and future screen gets it and none can forget it.
3. **What an old, version-less token does** — refused once (spec edge case).

### Order of work

Slice A → B → the constitution amendment → C → docs. The panel comes after the
server because its tests stub the new responses from the contract.

## 2. Alternatives considered

| Option | Why rejected |
|---|---|
| A denylist of revoked token ids (`jti`) | Needs a new table, a lookup on every request, and cleanup of expired rows, to give per-session revocation that the spec places out of scope |
| A server-side session table | Replaces the stateless design with a row read and written per request; far more change than one counter for the same "end all" behavior |
| Compare the token's `iat` with a `sessions_valid_after` timestamp | `iat` has one-second resolution, so the token returned by a password change would land in the same second as the revocation and be ambiguous; an integer has no such tie |
| Keep `204` and sign the operator out after a password change | Simpler server, but it forces a sign-in straight after every change and contradicts R-2 |
| Redirect on 401 inside each page | Every screen would repeat it and a new screen could omit it; one hook in the client covers all |
| Treat a version-less token as version 0 | Would leave every pre-upgrade token alive until the first revocation, which defeats the point on the very deployments that need it most |
| Read-modify-write the counter in Python | Two racing requests can write the same value and drop a revocation; a single SQL increment cannot |

## 3. Constitution compliance

| Principle | How it is satisfied |
|---|---|
| 1. Platform code is isolated | No OS-dependent code; the touched server files are checked with the principle's grep |
| 2. Data does not leave the buffer without a request | Not touched; no agent change |
| 3. Request window ≤ 4 hours | Not touched |
| 4. Buffer retention is bounded | Not touched |
| 5. Exchange is authenticated and encrypted | Strengthened: `require_operator` now also checks the session's version, and both new behaviors stay behind it, with tests for 401 without a token and with an ended one. Agent authentication is unchanged. TLS unchanged |
| 6. Inventory is versioned | Not touched |
| 7. Logic is testable without real hardware | In-memory SQLite fixtures and `vitest`; the multi-session cases use two real logins through the test client |
| 8. Every action is logged | `operator.password_change` (existing) and the new `operator.sessions_revoked`; detail carries no password. A session refused for its version is not audited, like any other 401 |
| 9. Language mode | Comments in English; the new Settings copy and the sign-in message in Russian; `docs/ru` canonical, `docs/en` in sync |
| 10. Honesty about boundaries | Section V's "password change does not end sessions" is replaced, in the same change, by what is still true: revocation is all sessions of one operator at once, and a session is not individually listed or ended (see below) |
| 11. API contract is the single source of truth | `contracts/openapi.yaml` regenerated in its own commit; the `/auth/password` response changes from `204` to `200` with `TokenResponse`, and `/auth/logout-all` is new |

The constitution changes by a **MINOR amendment (1.1.0)** through Section VII: a
new decision **D-9** recording the version counter and the alternatives above,
and the Section V bullet rewritten. It removes a limitation rather than adding
a principle, but a decision is added, which is the MINOR case. What remains
honest, and goes into Section V: only *all* of an operator's sessions can be
ended, not one; a session already stolen works until the counter is raised, the
operator changes the password, or it expires (8 hours by default); and
a token from before the upgrade is refused once.

**Violations:** none.

## 4. Affected modules

| Module | Change |
|---|---|
| `server/src/warden_server/models/operator.py` | `token_version` |
| `server/alembic/versions/` | New revision: `add_column` / `drop_column` |
| `server/src/warden_server/security.py` | `TokenClaims`, `create_access_token(subject, version)`, `decode_access_token` returns claims |
| `server/src/warden_server/api/deps.py` | `require_operator` compares versions |
| `server/src/warden_server/api/auth.py` | `login` issues the version; `POST /auth/password` returns a token and raises the version; `POST /auth/logout-all` |
| `server/tests/` | Updated JWT, login, and password-change tests; new revocation tests (§8) |
| `agent/` | **No change.** Suite run as a regression |
| `web/src/api/client.ts` | `setUnauthorizedHandler`, `changePassword` returns the token, `logoutAll` |
| `web/src/state/` | `AuthProvider` registers the hook and holds `sessionEnded`; `authContext.ts` gains the flag |
| `web/src/pages/` | `SettingsPage.tsx` (keep session, «Сеансы» card), `LoginPage.tsx` (message) |
| `web/src/lib/audit.ts` | Label for `operator.sessions_revoked` |
| `web/tests/unit/` | Client, settings, login, and audit tests |
| `contracts/openapi.yaml` | `/auth/password` response, `/auth/logout-all` |
| `docs/ru/`, `docs/en/` | Architecture (authentication, boundaries), usage (settings) |
| `.specify/memory/constitution.md` | 1.0.3 → 1.1.0: D-9, Section V bullet, version-history row |

## 5. Data formats

**Database:** `operators.token_version INTEGER NOT NULL DEFAULT 0`. No other
change. The token carries `ver` (integer) in addition to `sub` and `exp`.

**Endpoints:**

| Endpoint | Request | Success | Errors |
|---|---|---|---|
| `POST /api/v1/auth/password` | `{"current_password", "new_password"}` | **200 `TokenResponse`** (was 204) | unchanged: 400, 401, 422, 429 |
| `POST /api/v1/auth/logout-all` | none | 204 | 401 |

## 6. Interface

**Settings.**
* «Смена пароля»: on success the message reads «Пароль изменён. Остальные сеансы
  завершены.» and the operator stays signed in. The previous sentence about
  sessions staying valid, and the lifetime it quoted, go away.
* New card «Сеансы»: a sentence saying that ending all sessions signs the
  operator out on every device, this one included, and a «Завершить все сеансы»
  button. It asks «Завершить все сеансы, включая этот?» inline, with «Завершить»
  and «Отмена», before sending anything.

**Sign-in.** After the server refuses a session, the sign-in screen shows
«Сеанс завершён. Войдите снова.» above the form until the next sign-in.

## 7. Risks

| Risk | Mitigation |
|---|---|
| Every existing operator is signed out once on upgrade | Stated in the docs and in the spec's impact section; the panel handles it like any refused session, so they land on the sign-in screen with the message rather than a broken page |
| The redirect loops or flashes if several requests fail together | The hook is idempotent (clearing an already-cleared session), and `RequireAuth` redirects on the missing token; a test issues two refused requests and expects one sign-in screen |
| A 401 not caused by an ended session signs the operator out | A 401 with a token can only come from `require_operator`, so it always means the session is unusable; the wrong-current-password case is a 400 by design, and a login sends no token |
| Sessions stolen *before* the operator notices remain usable until revoked | The boundary stays in Section V, reworded; revocation is an operator's response, not detection (out of scope) |
| A password change now returns a credential, so its response must not be logged or cached | It is a `TokenResponse` exactly like login's, sent over the same TLS; no new logging is added, and audit `detail` carries neither passwords nor tokens (asserted) |
| Lost increment under concurrency | One SQL increment instead of read-modify-write |
| Changing a documented response (`204` → `200`) breaks a client that expected no body | The panel is the only client and changes in the same series; the contract commit records it |
| Later specs mint tokens elsewhere (operator management) and forget the version | `create_access_token` now requires the version, so a call without it does not type-check |

## 8. Verification plan

No platform collector is touched.

```bash
# server
cd server && ruff check . && ruff format --check . && mypy src alembic \
  && bandit -c pyproject.toml -r src \
  && pytest --cov=warden_server --cov-report=xml --cov-fail-under=80
diff-cover coverage.xml --compare-branch=main --fail-under=80

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
| A-1, A-2 | server integration: two logins; change the password with the first; the second gets 401 on a panel read, the first (using the returned token) gets 200 |
| A-3, A-4 | server integration: two logins; `logout-all` with the first; both get 401; a fresh login works |
| A-5 | server integration: a wrong current password, a too-short new one, and a throttled attempt each leave a second session working |
| A-6, A-11 | server unit: a token with no `ver`, a non-integer `ver`, a garbage token, and a token of an unknown user are all refused; integration: no token → 401 |
| Version arithmetic | server unit: a token one version behind and one ahead are both refused; `create_access_token` and `decode_access_token` round-trip subject and version |
| A-7 | server integration: `operator.password_change` and `operator.sessions_revoked` rows exist; no audit `detail` contains either password or a token |
| R-9 | server unit: the token's `exp` is unchanged by the version |
| Migration | round trip on SQLite and PostgreSQL; the column defaults to 0 for an existing row |
| A-8 | `vitest` (client): a 401 to a request with a token calls the hook once; a 401 to a login (no token) does not; `vitest` (context): the hook clears the session and sets `sessionEnded`; (login page) the message shows, and clears on sign-in |
| A-9 | `vitest` (settings): a successful change stores the returned token with the same username and shows the new message; a failed one stores nothing |
| A-10 | `vitest` (settings): «Завершить все сеансы» asks first, then calls `logout-all` and clears the session; «Отмена» sends nothing |
| Audit label | `vitest`: `operator.sessions_revoked` has a Russian name |
| Contract | `test_openapi_contract.py` equality |

**Checked only manually, and how far:** once on the real `docker compose` stack
(Caddy + PostgreSQL), through the proxy and in a real browser: two browsers signed
in, a password change in one, the other refused and returned to sign-in with the
message; "end all sessions"; a token from before the upgrade refused after it.
What this does not verify: behavior with several server processes (the counter
lives in the database, so it should hold, but only one process ran), and browsers
other than Chromium. Both are stated in `docs/{ru,en}/usage.md`.
