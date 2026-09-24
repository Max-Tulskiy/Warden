# Implementation plan: Operator management and roles

**Spec:** [./spec.md](./spec.md) · **Status:** done · **Date:** 2026-09-24

---

## 1. Approach

Three slices: roles and their enforcement, the account-management endpoints,
and the panel. **No agent source changes**: agents authenticate with their own
key, and no agent endpoint reads an operator's role. The agent's integration
*test* fixture creates an operator row and needs a role (see §4 and the last
risk).

### Slice A — roles and their enforcement on the server (R-1, R-7…R-9, R-12, R-14)

* `models/operator.py` gains `OperatorRole` (`admin`, `viewer`) and
  `OperatorStatus` (`active`, `disabled`), both `StrEnum`, stored the way
  `AgentStatus` is (`Enum(..., native_enum=False)`). `Operator.role` has **no
  default**: creating an operator without saying what it may do is an error,
  not a silent administrator. `Operator.status` defaults to `active`.
* A new Alembic revision (down-revision `d23c48cef8fe`) adds both columns.
  `role` is added with a temporary server default of `ADMIN`, which is what
  backfills every existing account (R-14), and the default is then dropped in
  the same revision with `batch_alter_table`, so the finished schema has none
  and `alembic check` finds the model and the migrations in agreement.
  `status` keeps its server default `ACTIVE`. Downgrade drops both columns.
* `api/deps.py`:
  * `require_operator` now also refuses an operator whose status is not
    `active`, with the same 401 as any other refusal. Disabling also raises the
    version (Slice B), so this is a second, independent reason an account's old
    sessions stop working, not the only one.
  * a new `require_admin` depends on `require_operator` and answers **403**
    (`Administrator role required`) for a viewer. 403, not 401, so the panel
    can tell "you may not" from "your session ended" and does not sign an
    observer out.
  * the role is read from the operator row on every request and is not in the
    token, so a change takes effect on the next request (R-12).
* Which endpoint needs which role:

  | Endpoint | Observer | Administrator |
  |---|---|---|
  | `GET /agents`, `GET /agents/{id}/events`, `GET /agents/{id}/inventory/changes`, `GET /events`, `GET /policy` | yes | yes |
  | `POST /auth/password`, `POST /auth/logout-all`, `GET /auth/me` | yes | yes |
  | `POST /enrollment-tokens`, `PATCH /agents/{id}`, `POST /agents/{id}/requests` | **no** | yes |
  | `GET /audit` | **no** | yes |
  | `/operators…` (Slice B) | **no** | yes |

  In code: `api/agents.py` (`create_enrollment_token`, `set_agent_status`) and
  `api/requests.py` switch from `require_operator` to `require_admin`;
  `api/audit.py`'s router-level dependency does the same, which is the one line
  spec 003 said would be the only place to narrow.
* `POST /auth/login` refuses a disabled operator with the existing 401 and the
  existing message, and audits it as `operator.login_failed` with the reason
  `disabled`. The password is verified first, so a wrong password on a disabled
  account still reads `bad_password`.
* `GET /api/v1/auth/me` returns `{username, role}`; the panel needs the role
  and cannot read it from the token (R-15).
* `services/bootstrap.py::ensure_seed_operator` creates the seed account as an
  administrator, explicitly.

### Slice B — account management (R-2…R-6, R-10, R-11, R-13)

A new router, `api/operators.py`, whose router-level dependency is
`require_admin`, so no handler can forget it. Schemas in `schemas/operator.py`.

* `GET /api/v1/operators` → `list[OperatorOut]` (`id`, `username`, `role`,
  `status`; never the hash), ordered by username.
* `POST /api/v1/operators` → 201 `OperatorOut`. Body `OperatorCreateIn`
  (`username`, `role`, `password`). The username matches
  `^[A-Za-z0-9][A-Za-z0-9._@-]{0,63}$`; the password is
  `MIN_PASSWORD_LENGTH`…`MAX_PASSWORD_LENGTH`, the constants the password
  change already uses. A username equal to an existing one ignoring case is a
  409. Audit `operator.created` (target the new username, `detail` = the role).
* `PATCH /api/v1/operators/{id}` → `OperatorOut`. Body `OperatorUpdateIn`
  (`role` and/or `status`, at least one, no other fields).
  * The operator addressed by the caller's own id is a **409** (R-10).
  * A role change writes `operator.role_changed` (`detail` = from, to).
  * Disabling raises `token_version` with the same single-statement increment
    `api/auth.py` uses, then writes `operator.disabled`; enabling writes
    `operator.enabled`. A role change does **not** raise the version: the role
    is read live, so it already applies on the next request.
  * Setting the value the account already has is a 200 and writes nothing, as
    for a station's status.
  * A missing id is a 404.
* `POST /api/v1/operators/{id}/password` → 204. Body `{new_password}`. Own id is
  a 409 (the settings form, which asks for the current password, is the way).
  It stores the new hash, raises `token_version`, clears the login throttle for
  that username and its `password-change:` key so a locked-out colleague can
  sign in with the new password, and writes `operator.password_reset`.
* The "at least one active administrator" guarantee is a consequence of two
  rules, not a separate check: only an active administrator can call these
  endpoints, and they cannot address themselves, so the caller always remains.
  A concurrent pair of administrators acting on each other at the same instant
  could defeat this (both checks pass before either commits); that is stated
  as a boundary rather than solved (§7).
* The single-statement version increment moves from a private helper in
  `api/auth.py` to `services/sessions.py`, so both routers share one
  implementation instead of two copies of the rule that must not drift.

### Slice C — panel (R-15, plus the panel side of R-8 and R-12)

* `api/client.ts`: `getMe`, `listOperators`, `createOperator`,
  `updateOperator`, `resetOperatorPassword`; types `Role`, `Operator`. Beside
  the existing `setUnauthorizedHandler`, a `setForbiddenHandler` is called on a
  403 to a request that carried a token.
* `state/auth.tsx` loads the role with `getMe` whenever a token is present and
  exposes `role` (`null` until known); the forbidden handler reloads it, so a
  demoted administrator's next refused action also removes what they can no
  longer use (R-12). `authContext.ts` gains `role`.
* `AppShell.tsx` shows «Журнал» and «Операторы» only to an administrator and
  shows the person's role next to their name (`администратор` /
  `наблюдатель`). New route `/operators`; new `RequireAdmin` wrapper for it and
  for `/audit`: while the role is unknown it shows nothing, for an observer it
  shows the notice «Недостаточно прав для просмотра этого раздела» inside the
  shell, and it never signs them out.
* Administrator-only controls disappear for an observer: the enrollment token
  button (`AgentsPage`), the window request form (`AgentDetailPage`), and the
  «Станции» card of `SettingsPage`.
* `OperatorsPage.tsx`: a table (name, role, status) and a creation form.
  Per row, for accounts other than the person's own: «Сменить роль» (a select
  with «Применить» / «Отмена»), «Отключить» (with an inline confirmation, as for
  stations) / «Включить», and «Сбросить пароль» (an inline field and «Применить»
  / «Отмена»). The person's own row says «это вы» and offers nothing. Server
  errors map to Russian messages: duplicate name, own account, refused input,
  no rights.
* `lib/audit.ts` gains Russian names for `operator.created`,
  `operator.role_changed`, `operator.disabled`, `operator.enabled`,
  `operator.password_reset`.

### Spec points this plan resolves

1. **403 versus 401** for an observer's refused request: 403, so the panel can
   explain it instead of ending the session.
2. **Where the role lives**: in the database and read on every request, not in
   the token. The cost is one column already loaded with the operator row; the
   benefit is R-12 with no token reissue and no version bump on a role change.
3. **Last administrator**: guaranteed by "administrators only, and never
   yourself", not by counting.
4. **Reset by an administrator versus change by the owner**: separate endpoints
   with different rules (no current password, but never your own), so the
   throttled current-password check cannot be bypassed for oneself.

### Order of work

Slice A → B → contract → the constitution amendment → C → docs.

## 2. Alternatives considered

| Option | Why rejected |
|---|---|
| Put the role in the token | A demotion would not apply until the token expired or the version was raised, contradicting R-12; reading one column that is already loaded is cheaper than any workaround |
| Bump the version on a role change | Signs a demoted person out although the live role check already applies the change; more disruptive for no added safety |
| Default `role` to administrator in the model | Any code path that creates an operator without thinking would silently create an administrator; a required argument makes that a visible error |
| Keep the temporary `ADMIN` server default on the column | Same hazard one level down: a raw `INSERT` would create administrators |
| Count active administrators and refuse the change that would leave none | Redundant with the no-self-change rule, and it would not close the concurrent case anyway under normal isolation |
| Allow deleting an account | Would orphan the actor and target names in the audit log; disabling covers the need |
| A second endpoint to list roles for the form | Two roles are a constant of the panel, like the action names; a contract entry adds surface for nothing |
| Hide administrator controls in the panel only | Fails R-9: a request sent directly would succeed; the server check is the control, the panel is a courtesy |
| One `PATCH` for password reset too | It would put a credential in a general update body next to role and status, and the "not yourself" rules differ |

## 3. Constitution compliance

| Principle | How it is satisfied |
|---|---|
| 1. Platform code is isolated | No OS-dependent code; the touched server files are checked with the principle's grep |
| 2. Data does not leave the buffer without a request | Not touched; an observer cannot place the request that makes an agent send data |
| 3. Request window ≤ 4 hours | Not touched; the window request endpoint keeps its validation and gains only an administrator check |
| 4. Buffer retention is bounded | Not touched |
| 5. Exchange is authenticated and encrypted | Strengthened: every operator endpoint still depends on `require_operator`, which now also refuses a disabled account, and privileged ones on `require_admin`. A test walks the whole OpenAPI schema and fails if any operation other than login, agent enrollment, and health lacks authentication, so a new endpoint cannot ship open. Passwords are stored as Argon2id hashes and never logged |
| 6. Inventory is versioned | Not touched |
| 7. Logic is testable without real hardware | In-memory SQLite fixtures with an administrator and an observer; `vitest` for the panel |
| 8. Every action is logged | `operator.created`, `operator.role_changed`, `operator.disabled`, `operator.enabled`, `operator.password_reset`; a refused sign-in of a disabled account is `operator.login_failed` with reason `disabled`. A 403 is not audited, like any other refused request |
| 9. Language mode | Comments in English; every new panel string, role name, and error in Russian; `docs/ru` canonical, `docs/en` in sync |
| 10. Honesty about boundaries | Section V gains three limits (below), stated in the docs and on the operators screen |
| 11. API contract is the single source of truth | `contracts/openapi.yaml` regenerated in its own commit: the operators paths, `/auth/me`, and 403 responses on the administrator-only operations |

The constitution changes by a **MINOR amendment (1.2.0)** through Section VII: a
new decision **D-10** (two roles, enforced by the server on every request, the
role kept in the database rather than the token), and three Section V
boundaries: an observer sees everything the complex has collected, only without
acting on it; an administrator knows an initial or reset password until the
person changes it, and nothing forces the change; and two administrators acting
on each other at the same instant could leave none active, which then needs
direct database access to repair.

**Violations:** none.

## 4. Affected modules

| Module | Change |
|---|---|
| `server/src/warden_server/models/operator.py` | `OperatorRole`, `OperatorStatus`, `role`, `status` |
| `server/alembic/versions/` | New revision: both columns, `role` backfilled to `ADMIN`, its default then dropped |
| `server/src/warden_server/api/deps.py` | `require_operator` refuses a disabled account; `require_admin` |
| `server/src/warden_server/api/{agents,requests,audit}.py` | Administrator-only where the table says so |
| `server/src/warden_server/api/auth.py` | `login` refuses a disabled account; `GET /auth/me` |
| `server/src/warden_server/api/operators.py` (new), `main.py` | The account endpoints; router registration |
| `server/src/warden_server/schemas/operator.py` (new), `schemas/auth.py` | `OperatorOut`, `OperatorCreateIn`, `OperatorUpdateIn`, `OperatorPasswordResetIn`, `MeOut` |
| `server/src/warden_server/services/sessions.py` (new) | The single-statement version increment, moved out of `api/auth.py` |
| `server/src/warden_server/services/bootstrap.py` | The seed account is an administrator, explicitly |
| `server/tests/` | Fixtures with an observer; the permission matrix; the open-endpoints guard; account tests; updated fixtures that create an operator (§8) |
| `agent/tests/integration/conftest.py` | The operator fixture passes `role` (test code only, no agent source) |
| `web/src/api/{client,types}.ts` | The new calls, types, and the forbidden hook |
| `web/src/state/{auth.tsx,authContext.ts}` | `role` and its reload |
| `web/src/components/AppShell.tsx`, `RequireAdmin.tsx` (new) | Role-aware navigation and guard |
| `web/src/pages/` | `OperatorsPage.tsx` (new); `AgentsPage`, `AgentDetailPage`, `SettingsPage` hide administrator controls |
| `web/src/lib/audit.ts` | Five new names |
| `web/src/App.tsx` | `/operators`, and `/audit` behind the guard |
| `web/tests/unit/` | Tests for each of the above |
| `contracts/openapi.yaml` | New paths and 403 responses |
| `docs/ru/`, `docs/en/` | Architecture (authorization, accounts, boundaries), usage (the Operators screen, roles) |
| `.specify/memory/constitution.md` | 1.1.0 → 1.2.0: D-10, three Section V bullets, version-history row |

## 5. Data formats

**Database:** `operators.role` (`ADMIN` \| `VIEWER`, not null, no default) and
`operators.status` (`ACTIVE` \| `DISABLED`, not null, default `ACTIVE`).

**Endpoints** (operator JWT; "admin" means the administrator role):

| Endpoint | Request | Success | Errors |
|---|---|---|---|
| `GET /api/v1/auth/me` | none | 200 `{username, role}` | 401 |
| `GET /api/v1/operators` | none | 200 `list[OperatorOut]` | 401, 403 |
| `POST /api/v1/operators` | `{username, role, password}` | 201 `OperatorOut` | 401, 403, 409 duplicate, 422 |
| `PATCH /api/v1/operators/{id}` | `{role?, status?}` | 200 `OperatorOut` | 401, 403, 404, 409 own account, 422 |
| `POST /api/v1/operators/{id}/password` | `{new_password}` | 204 | 401, 403, 404, 409 own account, 422 |
| `POST /enrollment-tokens`, `PATCH /agents/{id}`, `POST /agents/{id}/requests`, `GET /audit` | unchanged | unchanged | **403** for an observer added |

`OperatorOut` = `{id, username, role, status}`.

## 6. Interface

**Everywhere.** The person's role is shown next to their name. An observer's
sidebar lists «Станции», «Отчёты», «Настройки»; an administrator's also lists
«Журнал» and «Операторы».

**Операторы (`/operators`).**
* A table: Имя, Роль (`администратор` / `наблюдатель`), Статус (a pill: активен /
  отключён), Действия.
* «Создать оператора»: username, role (select), password, «Создать». A hint
  under it: the administrator knows this password until the person changes it
  after signing in.
* Row actions as in the plan above; the person's own row reads «это вы».
* States: loading; error («Не удалось загрузить операторов»); an action error
  under the table; no empty state, because the person is always in the list.

**No rights.** An observer who opens `/audit` or `/operators` by address sees the
shell with «Недостаточно прав для просмотра этого раздела».

## 7. Risks

| Risk | Mitigation |
|---|---|
| Upgrading locks everyone out | The migration backfills every existing account as an administrator, tested on SQLite and PostgreSQL with a row that existed before it |
| A new endpoint ships without authentication, or without the administrator check it needs | The open-operations guard (only login, enrollment, and health may be open); a parametrized matrix that calls every operator endpoint as both roles and asserts the table in §1; the matrix is the executable copy of that table |
| A hidden panel control gives a false sense of security | Every restriction is asserted at the HTTP level with a real observer token, independent of the panel |
| Two administrators disabling each other at the same instant leave none active | Stated as a boundary in Section V and the docs. Repair needs database access; not solved here, because a correct fix needs serializable transactions or row locking that this project's single-process deployment and test database do not exercise |
| The seed account, created from configuration, is the only administrator and its password is the deployment's | Existing advice stands (change it after first login); the operators screen lets it create a second administrator |
| An administrator's chosen initial password is known to them | Stated in the docs and next to the creation form; a forced first-login change is out of scope |
| A role change is not seen by an open browser until its next action | The next request is checked against the live role; a 403 makes the panel reload the role and drop what is no longer allowed |
| Passwords in request bodies could reach logs | No new logging is added; the audit `detail` carries roles and names only, asserted by a test that scans every audit row after each operation |
| Username lookalikes (`admin` vs `Admin`) | Uniqueness is checked ignoring case, and the character set is restricted |
| Existing tests create operators without a role and would fail | The shared fixtures, the seed-bootstrap test, and the agent's integration fixture pass a role explicitly, so the "no default" rule is enforced by the test suite too |
| Two operators are now possible, so the throttle keyed on username matters more | Unchanged and still per username; a password reset clears it for the account, so a locked-out colleague is not stranded |

## 8. Verification plan

No platform collector is touched.

```bash
# server
cd server && ruff check . && ruff format --check . && mypy src alembic \
  && bandit -c pyproject.toml -r src \
  && pytest --cov=warden_server --cov-report=xml --cov-fail-under=80
diff-cover coverage.xml --compare-branch=main --fail-under=80

# agent — no source change; runs against the real server code
cd agent && pip install --no-deps -e ../server   # keep the server editable
ruff check . && ruff format --check . && mypy src \
  && bandit -c pyproject.toml -r src && pytest

# panel
cd web && npm run lint && npm run format && npm test && npm run build

# migration, both directions, with an operator that existed before it
cd server && alembic upgrade head && alembic downgrade -1 && alembic upgrade head && alembic check
```

**Acceptance criteria → tests**

| Criterion | Test |
|---|---|
| A-1, A-2 (observer allowed and refused) | server integration, the permission matrix: each operator endpoint is called with an administrator token and an observer token and the result is compared with the table in §1 |
| A-3 | server integration: the observer changes their own password and ends their sessions |
| A-4 | server integration: the list shows every account with role and status and never a `password_hash` |
| A-5, A-6 | server integration and unit (`OperatorCreateIn`): a case-variant duplicate → 409 and nothing stored; a bad character, a too-short password, a too-long name → 422 |
| A-7, A-8 (role applies at once) | server integration: promote then use an administrator endpoint with the same token; demote then get 403 on it while an observer endpoint still returns 200 |
| A-9 | server integration: own role, own status, own password reset each → 409 and nothing changes |
| A-10, A-11 | server integration: disable → the old token and a login both 401; enable → login works; disabled with a wrong password audits `bad_password` |
| A-12 | server integration: reset → the old password and the account's session stop working, the new one signs in, and a throttled account is unlocked |
| A-13, A-14 | server integration: an audit row per kind; a repeated change adds none; no audit row contains any password |
| A-15 | migration test on SQLite and PostgreSQL with a pre-existing row: it reads `ADMIN` and `ACTIVE` |
| A-18 | server integration: unknown id → 404 on both id endpoints |
| Open endpoints guard | server integration: the operations in `app.openapi()` with neither a bearer security requirement nor an `X-Agent-Key` header are exactly login, enrollment, and health |
| `role` has no default | server unit: creating an `Operator` without a role fails |
| Contract | `test_openapi_contract.py` equality |
| A-16, A-17 (panel) | `vitest`: `getMe` populates the role; an observer's shell has no «Журнал» / «Операторы»; `/audit` and `/operators` show the no-rights notice; the enrollment button, the window form, and the stations card are absent for an observer and present for an administrator; the operators screen creates, changes role, disables (after confirmation), enables, and resets a password, maps 409 / 422 / 403 to Russian text, and offers nothing on the person's own row; a 403 reloads the role and a 401 still ends the session; the five new audit names exist |

**Checked only manually, and how far:** once on the real `docker compose` stack
(Caddy + PostgreSQL), through the proxy and in real browsers with an
administrator and an observer signed in side by side: creating the observer;
the observer's screens and the absence of controls; a direct request from the
observer's token refused; promotion and demotion applying on the next action;
disabling ending the observer's session; the audit screen showing the new
actions under their Russian names. What this does not verify: the concurrent
mutual-disable case, behavior with several server processes, and browsers other
than Chromium; all three are stated in `docs/{ru,en}/usage.md`.

## 9. Deviations found during implementation

* **A demotion does not raise `token_version`.** The high-level plan approved before
  this spec said a demotion should end the person's sessions. Once the role is read
  from the database on every request, a demotion already applies to the next
  request, so ending the session would only sign the person out for no added
  safety. Disabling still ends sessions; a role change does not. The manual pass
  confirmed a demoted session stays usable for an observer's actions.
* **The contract's 403 needed code, not just regeneration.** The plan said the
  contract would gain 403 responses; FastAPI does not derive one from a dependency
  that raises. `ADMIN_ONLY_RESPONSES` in `api/deps.py` is attached to the
  administrator-only routes and routers, and a test in the permission matrix fails
  when an administrator-only operation lacks it, so the contract states what the
  server does (principle 11).
* **`/operators` is routed with its page.** T-18 planned a placeholder route; the
  route was added in T-22 together with `OperatorsPage`, which avoided a throwaway
  screen.
* **The operators screen does not fetch the policy.** The plan implied a
  client-side minimum-length check; the password minimum lives in the policy
  endpoint, and a second source of that number in the panel would drift. The screen
  leaves the length check to the server and words the 422 message as "shorter than
  the minimum from settings" without a number.
* **Settings loads stations only for an administrator.** The single load effect was
  split so the station list is not requested at all for someone who cannot see the
  card, rather than fetched and hidden.
* **The agent's test fixture changed again**, for the same reason as in 004: it
  creates an operator, which now needs a stated role. The fixtures in
  `server/tests/conftest.py`, the seed-bootstrap test, and the agent's integration
  fixture all pass a role explicitly, which is the "no default" rule enforced by
  the test suite itself.
* Two test helpers needed a fix during the work, not the code: a default parameter
  swallowed an explicit `undefined` role in the navigation tests, and a text query
  in the stations-page tests matched both the menu item and the heading.
* The concurrent mutual-disable race was not reproduced; it stays a documented
  boundary, as planned.
