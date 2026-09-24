# Implementation plan: Editable operating policy

**Spec:** [./spec.md](./spec.md) · **Status:** done · **Date:** 2026-09-24

---

## 1. Approach

Three slices: where the values live and how every use reads them, the endpoints,
and the panel. **No agent source changes**: the agent keeps its own four-hour
check (`max_window_hours=4` in `warden_agent/__main__.py`), and the server can
never place a window above four hours, so the two stay consistent. The agent's
integration *fixture* mints an operator token with a function whose signature
changes (see §4 and the risks).

### Slice A — storage and one place that decides (R-2, R-3, R-6, R-10)

* **What is editable, and its bounds** (constants in `schemas/policy.py`, not
  settings): the request window `1…4` hours, the enrollment token lifetime
  `1…168` hours, the session lifetime `5…1440` minutes. **The upper bound of
  the window is the constitution's four hours and appears exactly once**, as
  `WINDOW_HOURS_CEILING`; it is a ceiling in code, not a value anyone edits.
* A new table `policy_overrides` (model `models/policy.py`, new Alembic
  revision, down-revision `afddc26b2815`): one row, `id` fixed at 1 by a check
  constraint, the three values `NOT NULL`, `updated_at`, `updated_by`. **No row
  means "nobody saved a policy"**; a row means all three values were saved
  together. There are no nullable columns and no per-field mixing, so "which
  value is in force" has one answer.
* `services/policy.py` is the only place that decides a value:
  * `configured_defaults()` — what `Settings` gives, with the window clamped to
    the ceiling (a configuration of 6 hours can never take effect, R-2);
  * `effective_policy(db)` — the saved row if there is one, else the defaults,
    plus whether a row exists (`overridden`);
  * `save_policy(db, values, actor)` and `reset_policy(db)` — write or delete
    the row and return what changed, for the endpoint to audit.
* Every use reads it, and nothing else reads the three `Settings` fields any
  more:
  * `api/requests.py::create_window_request` compares the requested window with
    `effective_policy(db).max_request_window_hours` and answers 422;
    `WindowRequestIn` (`schemas/task.py`) stops reading `Settings` and checks only
    the constant ceiling, so principle 3's "server refuses over four hours" holds
    with no database at all and its existing tests stay as they are;
  * `api/agents.py::create_enrollment_token` uses the effective token lifetime;
  * `security.py::create_access_token(subject, version, lifetime)` now takes the
    lifetime as a **required** argument instead of reading `Settings`; `login`
    and `change_password` pass `timedelta(minutes=effective_policy(db)…)`. A
    caller that forgets it does not type-check, which is what keeps a second
    source of the value from creeping back in.
* A change applies from the next use because each use reads the row afresh: no
  cache, so it is also correct across several server processes. Tokens, sessions
  and queued tasks already carry their own expiry or window, so they are
  untouched (R-3).

### Slice B — endpoints (R-1, R-4…R-9)

In `api/policy.py`; the router keeps `require_operator` for reading, and the two
writes add `require_admin` and `ADMIN_ONLY_RESPONSES` (spec 005).

* `GET /api/v1/policy` → `PolicyOut`. The seven existing flat fields keep their
  names and now show the value **in force**; three fields are added:
  `overridden` (a saved policy exists), `defaults` (the three values from the
  server's configuration), and `bounds` (`{min, max}` for each of the three). The
  panel needs the bounds and the defaults, and reading them from the server keeps
  them from being copied into the panel (as the minimum password length already
  is). Still an explicit allow-list schema; no secret can appear.
* `PUT /api/v1/policy` → 200 `PolicyOut`. Body `PolicyUpdateIn`: the three values,
  all required, whole numbers only (strict integers, so `2.5` and `"2"` are
  refused), each within its bounds, no other field. It stores all three.
  * The audit entry `policy.changed` carries `{field: [old, new]}` for each value
    that changed, plus `"overridden": [false, true]` when this save created the
    row. Saving what is already in force, twice, writes nothing the second time.
  * A first save that equals the defaults still creates the row (it changes who
    decides), and is audited through the `overridden` line.
  * Two administrators saving together: the later write wins and each is audited.
    The first-ever insert can race; the unique key makes the loser retry once.
* `DELETE /api/v1/policy` → 200 `PolicyOut`: removes the row, so the server's
  configured values apply again. Audited as `policy.reset` with `{field: [old,
  default]}` for the values that differ and `"overridden": [true, false]`; with no
  row it does nothing and writes nothing.
* Without this reset, an administrator's one save would make later edits to the
  server's configuration silently ineffective; that trap is why it is in scope.

### Slice C — panel (R-4, R-5, R-7, R-10, R-11, R-12)

* `client.ts`: `savePolicy`, `resetPolicy`; `Policy` gains `overridden`,
  `defaults`, `bounds`.
* `SettingsPage.tsx`, the «Политика сервера» card:
  * for an administrator, the three editable values become number inputs, each
    with its unit, its range («от 1 до 4 ч»), and the configured value
    («по умолчанию: 8 ч»), and buttons «Сохранить» and, when a policy is saved,
    «Сбросить к значениям сервера» (with an inline confirmation);
  * the client checks whole-number and range before sending and names the range;
  * on success: «Политика сохранена. Новый предел окна действует для следующих
    запросов, срок сеанса — для новых входов, срок токена — для новых токенов;
    уже выданные сеансы, токены и запросы сохраняют свой срок.»;
  * for an observer, and for the values that are not editable, the read-only rows
    stay, with the footer «Пределы загрузки, размер страницы и минимальная длина
    пароля задаются конфигурацией сервера и из панели не меняются.»
* `AgentDetailPage.tsx` loads the policy and passes the window limit to
  `WindowRequestForm`, which shows it and `validateWindow` checks against it. The
  fixed `MAX_WINDOW_HOURS` stays only as the fallback when the policy cannot be
  loaded; the server still enforces the real limit.
* `lib/audit.ts`: names for `policy.changed` and `policy.reset`.

### Spec points this plan resolves

1. **"Cannot exceed four hours whatever is configured"** — the ceiling is a
   constant; the configured default is clamped to it and a saved value is
   validated against it. Three places each reduce to that one constant.
2. **Whole set or single values** — a saved policy is all three values together,
   so there is no state where one value is saved and another follows the
   configuration, and the reset is one action.
3. **Configuration versus saved values** — saved wins until reset; the panel shows
   the configured value beside each field so the administrator can see what a
   reset returns to.
4. **Where "applies to the next use" is enforced** — nowhere specially: every use
   reads afresh and existing artifacts carry their own expiry.

### Order of work

Slice A → B → contract → the constitution amendment → C → docs.

## 2. Alternatives considered

| Option | Why rejected |
|---|---|
| Nullable per-field overrides (a value not set follows the configuration) | Two sources per field and a table of which one wins; a full set saved together has one answer and one reset |
| Make the four-hour ceiling a setting | Principle 3 fixes it; a setting can be raised by whoever can save one |
| Validate the window limit inside `WindowRequestIn` | A schema validator has no database session; it would need a global or a second settings read, which is the two-sources problem again |
| Keep `create_access_token` reading `Settings` and patch the cache | The lifetime would come from a process-wide cache that a save cannot reliably invalidate across processes |
| Cache the effective policy in memory | Wrong across several server processes and after a restart-less change; the read is one small query on paths that are not hot |
| Give `create_access_token` an optional lifetime defaulting to `Settings` | A forgotten argument would silently use the configuration and ignore a saved policy |
| Let the panel hard-code the bounds | They would drift from the server's; the minimum password length already showed the better pattern |
| Ending existing sessions when the session length is shortened | The spec puts it out of scope; sessions carry their expiry and the reset/revoke tools exist |
| An "undo last change" | The audit log records old values; a reset to the configured values covers the operational need |
| Store the policy in `Settings` written back to a file | The server would need write access to its own configuration and a restart to apply it |

## 3. Constitution compliance

| Principle | How it is satisfied |
|---|---|
| 1. Platform code is isolated | No OS-dependent code; the touched server files are checked with the principle's grep |
| 2. Data does not leave the buffer without a request | Not touched; a lower window limit only makes each request smaller |
| 3. Request window ≤ 4 hours | **Strengthened, not loosened.** `WINDOW_HOURS_CEILING = 4` is a constant; `WindowRequestIn` rejects over it with no database; the endpoint additionally enforces the saved limit, which validation keeps within `1…4`; the configured default is clamped to it. The agent's own check is untouched. Tests: a 4-hour-1-minute window is refused with no policy saved; a saved limit of 5 is refused; a configured 6 does not take effect |
| 4. Buffer retention is bounded | Not touched |
| 5. Exchange is authenticated and encrypted | Reads need an operator token; both writes need an administrator (403 for an observer, asserted by the permission matrix, which gains rows for them). Session and enrollment lifetimes are bounded (`5…1440` minutes, `1…168` hours), so an administrator cannot make either unbounded |
| 6. Inventory is versioned | Not touched |
| 7. Logic is testable without real hardware | In-memory SQLite fixtures; the effective-policy service is tested directly and through the API; `vitest` for the panel |
| 8. Every action is logged | `policy.changed` and `policy.reset`, with old and new values, none when nothing changed. Reads are not logged, as elsewhere |
| 9. Language mode | Comments English; every panel string in Russian; `docs/ru` canonical with `docs/en` in sync |
| 10. Honesty about boundaries | Section V gains three limits (below) and the docs state them beside the form |
| 11. API contract is the single source of truth | `contracts/openapi.yaml` regenerated in its own commit: the two writes, the three new response fields, the 403 |

The constitution changes by a **MINOR amendment (1.3.0)** through Section VII: a
new decision **D-11** (the three operating limits are stored in the database and
edited by administrators within fixed bounds; the four-hour window ceiling is a
constant; the server's configuration is the default) and three Section V
boundaries: a change applies to what is issued or placed afterwards and never to
sessions, tokens, or requests that already exist; the policy is one set for the
whole deployment and its only history is the audit log; and a saved policy
outranks the server's configuration until it is returned to it, so editing the
configuration alone changes nothing once someone has saved.

**Violations:** none.

## 4. Affected modules

| Module | Change |
|---|---|
| `server/src/warden_server/schemas/policy.py` | Bounds and the ceiling as constants; `PolicyValues`, `PolicyBounds`, `PolicyUpdateIn`; `PolicyOut` gains `overridden`, `defaults`, `bounds` |
| `server/src/warden_server/models/policy.py` (new), `models/__init__.py`, `alembic/env.py` | `PolicyOverride`; imported so metadata and migrations see it |
| `server/alembic/versions/` | New revision: `policy_overrides` with the singleton check |
| `server/src/warden_server/services/policy.py` (new) | `configured_defaults`, `effective_policy`, `save_policy`, `reset_policy` |
| `server/src/warden_server/api/policy.py` | `GET` shows the values in force plus the new fields; `PUT`, `DELETE` |
| `server/src/warden_server/api/requests.py`, `api/agents.py` | Read the effective limit and token lifetime |
| `server/src/warden_server/schemas/task.py` | `WindowRequestIn` checks the constant ceiling only |
| `server/src/warden_server/security.py`, `api/auth.py` | `create_access_token` takes a required lifetime; `login` and `change_password` pass the effective one |
| `server/tests/` | Updated policy, JWT, and token tests; new tests (§8); permission matrix rows |
| `agent/tests/integration/conftest.py` | The operator token fixture passes a lifetime (test code only) |
| `web/src/api/{client,types}.ts` | `savePolicy`, `resetPolicy`; the new `Policy` fields |
| `web/src/pages/SettingsPage.tsx`, `AgentDetailPage.tsx` | The editable policy card; the window limit passed to the form |
| `web/src/components/WindowRequestForm.tsx`, `web/src/lib/windowValidation.ts` | Take the limit as a parameter |
| `web/src/lib/audit.ts` | Two names |
| `web/tests/unit/` | Tests for each of the above |
| `contracts/openapi.yaml` | `PUT` and `DELETE /policy`, `PolicyOut` |
| `docs/ru/`, `docs/en/` | Architecture (policy, boundaries), usage (Settings) |
| `.specify/memory/constitution.md` | 1.2.0 → 1.3.0: D-11, three Section V bullets, version-history row |

## 5. Data formats

**Database:** `policy_overrides(id PK check id = 1, max_request_window_hours INT NOT
NULL, enrollment_token_ttl_hours INT NOT NULL, session_lifetime_minutes INT NOT
NULL, updated_at, updated_by)`.

**Endpoints** (operator JWT; writes need the administrator role):

| Endpoint | Request | Success | Errors |
|---|---|---|---|
| `GET /api/v1/policy` | none | 200 `PolicyOut` | 401 |
| `PUT /api/v1/policy` | `{max_request_window_hours, enrollment_token_ttl_hours, session_lifetime_minutes}`, whole numbers in range, nothing else | 200 `PolicyOut` | 401, 403, 422 |
| `DELETE /api/v1/policy` | none | 200 `PolicyOut` | 401, 403 |
| `POST /agents/{id}/requests` | unchanged | unchanged | **422 added** when the window exceeds the limit in force |

`PolicyOut` = the seven existing flat fields (the three editable ones now the value
in force) plus `overridden`, `defaults` (the three), and `bounds` (`{min, max}` per
editable value).

## 6. Interface

**Настройки → «Политика сервера».**
* An administrator sees three rows with inputs. Each shows its unit, «от 1 до 4»,
  and «по умолчанию: 8 ч». «Сохранить» sends all three. When a policy is saved,
  a note says so and «Сбросить к значениям сервера» appears; it asks first,
  naming what it returns to.
* Below, the read-only rows for the limits that stay in the configuration, and the
  footer sentence that says so.
* An observer sees all values as rows, with no inputs or buttons.
* States: loading; a policy that cannot be loaded (the card says so; the other
  cards work); a rejected save (names the range or «Недостаточно прав»).

**Станция → форма запроса данных.** «Промежуток не должен превышать N ч» with the
limit in force; a longer window is refused before sending.

## 7. Risks

| Risk | Mitigation |
|---|---|
| A configured window above four hours used to be honored and is now clamped | That value was already contrary to principle 3 and to the agent, which refuses over four hours; the clamp is stated in the docs and asserted by a test |
| A compromised administrator session weakens security by lengthening sessions or token lifetimes | Bounded (`24 h` sessions, `7 d` tokens), audited with old and new values, and reversible; the four-hour ceiling cannot move |
| Someone sets the session to 5 minutes and locks everyone into constant sign-ins | Bounded below at 5 minutes; «Сбросить к значениям сервера» is one action; the panel already returns to sign-in on an ended session |
| After a save, editing the configuration appears to do nothing | Stated on the card and in the docs; the reset exists for exactly this, and the configured value is shown beside each field |
| `create_access_token` gains a required argument, so every minting site changes | A missing argument fails type checking and a test; the two production sites and the test fixtures are updated together |
| Concurrent first saves race on the singleton row | The loser retries once; a test simulates the failed insert |
| The window form and the server disagree if the limit changes while the form is open | The server is the authority and answers 422; the panel shows a refusal, and the next load shows the new limit |
| The policy read adds a query to login, token issue, and window requests | One indexed primary-key read per use; none of these is a hot path |
| `PolicyOut` grows and an old panel build sees extra fields | Added fields are ignored by a client that does not know them; the panel and server ship together |
| Default and bounds could drift between panel and server | The panel takes both from `GET /policy`; no number is copied into it except the fallback four hours |

## 8. Verification plan

No platform collector is touched.

```bash
# server
cd server && ruff check . && ruff format --check . && mypy src alembic \
  && bandit -c pyproject.toml -r src \
  && pytest --cov=warden_server --cov-report=xml --cov-fail-under=80
diff-cover coverage.xml --compare-branch=main --fail-under=80

# agent — no source change; runs against the real server code
cd agent && pip install --no-deps -e ../server
ruff check . && ruff format --check . && mypy src \
  && bandit -c pyproject.toml -r src && pytest

# panel
cd web && npm run lint && npm run format && npm test && npm run build

# migration, both directions
cd server && alembic upgrade head && alembic downgrade -1 && alembic upgrade head && alembic check
```

**Acceptance criteria → tests**

| Criterion | Test |
|---|---|
| A-1 | server integration: save a limit of 2 hours; a 3-hour request → 422 and a 2-hour one → 201 |
| A-2 | server unit and integration: a saved limit of 5, 0 and −1 → 422, nothing stored; the constant ceiling is 4 |
| A-3 | server unit: a configured 6 is clamped to 4 in `configured_defaults` and `effective_policy`; integration: a 5-hour request → 422 with nothing saved |
| Principle 3 | the existing 4h-1min schema tests pass unchanged; a schema test proves `WindowRequestIn` does not read `Settings` |
| A-4, A-5 | server integration: save 30 minutes, log in, decode `exp`; a token issued before the change keeps its `exp` and still works |
| A-6 | server integration: save 2 hours, issue a token, and read its expiry; one issued earlier is unchanged |
| A-7 | server unit and integration: each field below its minimum, above its maximum, a float, a numeric string, a boolean, a missing field, and an extra field → 422, nothing stored |
| A-8 | server integration: before any save, `overridden` is false and the values equal the configuration; after, true with the saved values, and `defaults` and `bounds` alongside; the response has exactly the allow-listed fields and no secret |
| A-9, A-10 | server integration: a reset restores the configured values; with the settings object changed after a save, the saved values stay in force |
| A-11 | server integration and the permission matrix: an observer gets 200 on `GET` and 403 on `PUT` and `DELETE`; no token → 401 |
| A-12, A-13 | server integration: an identical second save adds no audit row; `policy.changed` and `policy.reset` carry the old and new values and `overridden`; a reset with nothing saved adds nothing |
| A-18 | migration test: an existing database upgrades with no `policy_overrides` row and the same values in force |
| Race | server unit: a failed first insert is retried once and the save succeeds |
| Callers | server unit: `create_access_token` needs a lifetime; both production callers use the effective one |
| Contract | `test_openapi_contract.py` equality, and the matrix's 403-documented test |
| A-14…A-17 (panel) | `vitest`: the card shows the three inputs, units, ranges, and defaults for an administrator and rows only for an observer; a save sends all three and shows the message; a range or non-integer error names the range and sends nothing; the reset asks first and then calls `DELETE`; a 403 shows «Недостаточно прав»; the window form shows and checks the limit in force, and falls back to four hours when the policy cannot be loaded; the two audit names exist |

**Checked only manually, and how far:** once on the real `docker compose` stack
(Caddy + PostgreSQL), through the proxy and in real browsers: an administrator
lowers the window and the session length; a longer window request is refused and
the form shows the new limit; a held session survives its own expiry unchanged
while a new sign-in gets the new length; the reset restores the configured values;
an observer sees no inputs; the audit screen shows both actions under Russian
names. What this does not verify: several server processes, browsers other than
Chromium, and the first-save race under real concurrency; all three are stated in
`docs/{ru,en}/usage.md`.

## 9. Deviations found during implementation

* **A filter group for the new actions.** The plan named only two audit labels.
  The audit screen's group filter also needed a group, or a test that every action
  falls under one would fail, so `policy` («Изменения политики») joined the four
  existing groups.
* **The panel's policy card is its own component**, `PolicyCard`, with
  `lib/policyFormat.ts` beside it, rather than more code in `SettingsPage`; the
  editor inside is rebuilt from a key when a save or a reset changes the policy,
  which avoids keeping a form in step with server state through an effect.
* **The policy form turns off the browser's own validation** (`noValidate`). A
  value like `2.5` with `step=1` was stopped by the browser before the panel could
  name the range; the panel now checks, and the server still checks too.
* **Two tests were too weak and were tightened.** The range tests for the policy
  form matched the hint printed beside each field, so they passed even when no
  error appeared; they now look for the error element. In the same spirit, a
  parameter default in a test helper had swallowed an explicit `undefined` in
  spec 005, fixed there.
* **`422` is written as the number.** FastAPI's newer constant name is missing in
  older releases the project still declares support for (`fastapi>=0.115`), and
  the older name is deprecated in newer ones.
* **An older migration test was brittle and was pinned.** The roles migration's
  downgrade test rolled back `-1` from the head; a newer revision made that a
  different migration. It now names its revision.
* **The docs were wrong about `.env` and were corrected.** The first draft said the
  three variables could be edited in `.env`; the shipped `docker-compose.yml`
  forwards only some variables to the server, not these three. Both languages now
  say so and how to add them.
* **The agent's test fixture changed again**, for the same reason as in specs 004
  and 005: `create_access_token` gained a required argument, `lifetime`, and the
  fixture mints an operator token. No agent source changed.
* **A wrong wait in the manual pass, not in the code.** After the server container
  was recreated the check waited on `/health`, which the proxy serves from the web
  container, so the script went on before the server was up; it was rerun once the
  server was ready. The first save race stays covered by the unit test only.
* **The contract also changed descriptions.** The docstrings of `WindowRequestIn`
  and the policy operations are part of the schema, so their rewording shows up as
  removed and added description lines beside the new operations.
