# Architecture

The canonical text is in Russian; see [../ru/architecture.md](../ru/architecture.md).
This document builds on the [project constitution](../../.specify/memory/constitution.md);
where the two disagree, the constitution wins.

## Overall layout

```
Workstation (Windows 10/11, Linux)              docker-compose
┌───────────────────────────────┐        ┌──────────────────────────────┐
│ warden-agent (service)        │        │ Caddy (TLS proxy, port 443)   │
│  ┌─────────────┐  ┌─────────┐ │        │   ├─ /api/* → server:8000     │
│  │ collectors  │→ │ buffer  │ │  HTTPS │   └─ /*     → web:80          │
│  │ (5 categ.)  │  │ SQLite  │ │──────▶ │                                │
│  └─────────────┘  └─────────┘ │ outbound   ┌────────────────────────┐  │
│         scheduler              │        │  │ FastAPI (server:8000)  │  │
└───────────────────────────────┘        │  │  ├─ agent endpoints     │  │
                                          │  │  ├─ operator endpoints  │  │
                                          │  └──┴─ PostgreSQL          │  │
                                          │      (server:8000 inside)  │  │
                                          │  web panel (web:80, React) │  │
                                          └──────────────────────────────┘
```

The agent never accepts an inbound connection -- it only ever initiates
outbound HTTPS requests to the server. This is the active-agent model, after
Zabbix (constitution D-1): chosen because a real workstation almost always
sits behind NAT or a corporate firewall, where a direct server-to-agent
connection is not workable in practice.

## The agent-server exchange, end to end

1. **Enroll.** An administrator issues a one-time enrollment token in the
   panel (`POST /api/v1/enrollment-tokens`). On first start, the agent trades
   that token for a permanent per-agent key (`POST /api/v1/enroll`). The
   server stores only the key's hash.
2. **Poll.** Every `poll_interval_seconds` (60s by default) the agent
   requests `GET /api/v1/agents/{id}/tasks`. The server returns any pending
   tasks and marks them dispatched.
3. **Collect.** Independently of polling, the agent's collectors write
   events to a local SQLite buffer continuously. The buffer keeps data no
   longer than `retention_hours` (8h by default, never less than 4h -- the
   request-window cap).
4. **Answer a window request.** On receiving a `window_request` task, the
   agent **re-checks** that the window does not exceed 4 hours (a deliberate
   double check, constitution principle 3), selects buffered events across
   every category for that window, and sends them via
   `POST /api/v1/agents/{id}/reports`.
5. **Inventory and heartbeat.** Separately from events, every
   `inventory_interval_seconds` (1h by default) the agent sends a
   hardware/software snapshot (`POST /api/v1/agents/{id}/inventory`), which
   also updates the agent's last-seen timestamp.

## Server data model

| Table | Purpose |
|---|---|
| `agents` | One row per enrolled agent: hostname, OS, key hash, status, last seen |
| `enrollment_tokens` | One-time enrollment tokens with an expiry |
| `tasks` | The task queue (currently only `window_request`), status pending/dispatched/completed/failed |
| `events` | Category events (`removable_media`, `printing`, `processes`, `web`), tied to the task they answered |
| `inventory_snapshots` | Full hardware/software snapshots, append-only, never overwritten |
| `inventory_changes` | Separate records of detected changes (added/removed/modified) |
| `operators` | Panel accounts: a role (`role`: administrator or observer), a status (`status`: active or disabled), and `token_version`, the counter whose increase ends all of an operator's sessions |
| `policy_overrides` | The policy an administrator saved: the window limit, the enrollment token lifetime, and the session lifetime as one set (at most one row; no row means the server's configuration applies) |
| `audit_log` | Every notable action: enrollment, task dispatch, login, configuration changes; read in the panel on the "Журнал" (audit log) screen |

### Configuration-change detector

On every inventory snapshot, the server computes the SHA-256 of the
canonical (sorted-key) JSON form of `{hardware, software}` and compares it
against the station's last saved snapshot's hash:

- hashes match → only `last_seen_at` is updated, no new change record;
- hashes differ (or this is the station's first snapshot) → a new snapshot is
  stored **and** a separate `inventory_changes` row records a per-key diff
  under `hardware` and `software`.

This is how the assignment's "store hardware/software information separately
to detect configuration changes" requirement is implemented -- snapshots
never overwrite each other, the full history stays visible, and a change is
immediately visible to the administrator as its own record.

## Panel reports and settings

**The cross-station report** (`GET /api/v1/events`) shows the events of one,
several, or all stations over an arbitrary period. Parameters: `start` and
`end` (required), `agent_id` (repeatable), `category`, `limit`/`offset`. The
range is half-open, `[start, end)`, like the window-boundary check when an
agent's report is accepted. Rows are ordered by `(occurred_at, id)`, so paging
neither loses nor repeats events that share a timestamp. Each row carries
`agent_id` and the station's *current* name (the name is not versioned). The
4-hour cap does not apply to the report: it governs the request the server
places with an agent (principle 3), while the report only reads what is
already stored, so a week-long range is allowed. `events` has an index,
`ix_events_occurred_at`, for the time lookup.

**The server policy** (`GET /api/v1/policy`). An administrator changes three
values from the panel: the request-window limit (1-4 hours), the lifetime of an
enrollment token (1-168 hours), and the lifetime of a session (5-1440 minutes).
They are stored in the database as one set (`policy_overrides`, at most one row);
the server's configuration (`WARDEN_MAX_REQUEST_WINDOW_HOURS`,
`WARDEN_ENROLLMENT_TOKEN_TTL_HOURS`, `WARDEN_JWT_EXPIRE_MINUTES`) gives their
defaults, and a saved set outranks the configuration until it is reset. One place,
`services/policy.py`, decides which value is in force; every use (a window
request, a token issue, a sign-in) reads it afresh, with no cache, so a change
applies from the next use and is right across several server processes. Sessions,
tokens, and requests that already exist keep their own lifetime or limit.

The four-hour window ceiling is a constant in code, not a setting (principle 3): the
server checks it on its own, without the database; a configured value above 4 is
clamped to 4; a value above 4 cannot be saved; and the agent still checks its own
limit independently. The limit an administrator may have lowered is applied by the
window-request endpoint (a 422, "the request window must not exceed N hours").

Operations: `GET` returns the values in force, `overridden` (whether a policy is
saved), `defaults` (the configured values a reset goes back to), and `bounds` (the
ranges); `PUT` saves all three values (whole numbers within their ranges only, no
extra fields; saving what is already in force writes nothing to the audit log);
`DELETE` resets the set to the configuration. Saving and resetting are for
administrators only (a 403 otherwise); the log records `policy.changed` (the old
and new value of each changed one) and `policy.reset`. The other limits -- the
minimum password length and the limits on an agent report, an inventory snapshot,
and a page of results -- stay in the code and cannot be changed from the panel. The
response is an explicit list of fields rather than a dump of the settings, so a
secret (`jwt_secret`, the database connection string) cannot reach it by accident.
The window request form in the panel takes the limit in force from the server and
checks against it before sending; if the policy could not be loaded it shows 4
hours, and the server still applies the real limit.

**Disabling a station** (`PATCH /api/v1/agents/{id}` with status `disabled` or
`active`). Enforcement is the existing `require_agent` dependency: an agent
that is not `active` gets the same 401 as one presenting a wrong key. The key
is not changed by disabling, so re-enabling puts the station back to work
without a new enrollment. A real status change is written to the audit log
(`agent.disabled`, `agent.enabled`); setting the status it already has is
not. The agent itself does not crash on a 401: its scheduler loop catches the
exception, the error goes to its local log, and polling carries on.

## Audit log

The server writes every notable action to `audit_log` (principle 8): station
enrollment, task dispatch, receipt of a report or an inventory snapshot, a
detected configuration change, an operator's login and password change, a
window request, an enrollment-token issue, and disabling or enabling a station.
The log can be read in the panel ("Журнал") or through `GET /api/v1/audit`.

Query parameters: `start` and `end` (required), `actor`, `action`,
`limit`/`offset`. The range is half-open, `[start, end)`, like the cross-station
report. Rows are ordered newest first, by `(occurred_at DESC, id)`, so paging
neither loses nor repeats entries that share a timestamp. `actor` is matched
exactly and can be an operator's username, a station id, or the hostname
announced while registering. `action` is either an exact code
(`operator.login`) or a group, that is, the part of a code before its first dot
(`operator` matches every `operator.*`). A plain string prefix would return
`operator.login_failed` together with `operator.login`, so a group is matched
only at the dot. The four-hour cap does not apply to reading the log: it governs
the request the server places with an agent (principle 3). `audit_log` has an
index, `ix_audit_log_occurred_at`, for the time range.

The panel shows actions under Russian names; a code with no name (for example,
one added by a newer server version) is shown as it is, so an entry is never
hidden. A station id in the "Кто" (who) and "Объект" (target) columns is replaced
by the station's hostname when the station list has loaded. Reading the log is
not itself written to it, like every other read in the panel.

## Authentication

Two independent mechanisms (constitution principle 5):

- **Agents** — an `X-Agent-Key` header carrying the permanent key issued at
  enrollment. The server stores only its SHA-256 hash and compares it via
  `hmac.compare_digest` (constant-time). The key must match the specific
  `agent_id` named in the request path -- otherwise one agent's key would
  work against every other agent's endpoints.
- **Operators** (the panel) — a JWT issued on login
  (`POST /api/v1/auth/login`). Passwords are stored with Argon2id.

Every failed login is written to `audit_log` as `operator.login_failed` (a
reason only -- "unknown user" or "bad password" -- never the password
itself), and after five failures in five minutes for that username the
server answers 429 and logs `operator.login_throttled`; even a correct
password does not bypass an active throttle (`services/throttle.py`). The
counter lives in the process's own memory: accurate for the shipped
deployment (uvicorn without `--workers`), but running multiple workers or
replicas would multiply the effective limit, and a restart clears it -- an
honestly documented limitation (constitution principle 10), not a solved
problem.

An operator changes their own password through `POST /api/v1/auth/password`
(a valid token is required). The server re-verifies the current password with
Argon2id; the new password must be at least 12 and at most 1024 characters
and differ from the current one. A wrong current password is a 400 (not a 401,
so the panel does not mistake it for an expired session) and is logged as
`operator.password_change_failed`; a successful change is logged as
`operator.password_change`. Repeated failures are limited by the same
mechanism as login (five in five minutes, a 429 response,
`operator.password_change_throttled`), but under a key of its own: the holder
of a stolen token cannot use this endpoint to lock the real operator out of
login. The passwords themselves never reach the log. The seed account from
`WARDEN_SEED_ADMIN_*` is created only when the operators table is empty, so
restarting the container does not bring the old password back.

**Sessions.** An operator's session is a JWT with the claims `sub`, `exp` and
`ver`, where `ver` is the value of `operators.token_version` at the time it was
issued. `require_operator` answers with the same 401 as for any invalid token
when `ver` is missing, is not an integer, or differs from the operator's
current value (decision D-9 of the constitution). Raising that one number
therefore ends all of an operator's sessions at once, and two operations raise
it. A successful password change answers 200 with a token for the new version:
the session that made the change carries on, and the others get a 401 on their
next request. `POST /api/v1/auth/logout-all` (204) ends every session,
including the current one, and logs `operator.sessions_revoked`. A failed
password change (400, 422, 429) ends nothing. The increment is a single SQL
statement, `token_version = token_version + 1`, not a read-modify-write in
Python, so two simultaneous requests cannot drop a revocation. The session
lifetime (`jwt_expire_minutes`, 8 hours by default) is unchanged. A token
issued before versions existed has no `ver` and is refused once after the
server is upgraded: the operator simply signs in again.

The panel handles a refusal in one place. When the server answers 401 to a
request **that carried a token**, the API client calls a registered handler,
which clears the session, and `RequireAuth` sends the operator to the sign-in
screen with the message "Сеанс завершён. Войдите снова." (the session has
ended, sign in again). A sign-in with a wrong password (a 401 with no token) and
a wrong current password on the change form (a 400) do not count as a refused
session. A single session cannot be ended on its own -- only all of them.

All external traffic runs over TLS, terminated at the Caddy reverse proxy
(`docker-compose.yml`, `Caddyfile`), not by the application server itself.

## Authorization and accounts

An operator account has one of two roles (decision D-10 of the constitution).

| What may be done | Observer | Administrator |
|---|---|---|
| Stations, reports, inventory changes, the server policy (read-only) | yes | yes |
| Changing one's own password, ending one's own sessions, `GET /api/v1/auth/me` | yes | yes |
| Requesting data from a station, issuing an enrollment token, disabling and enabling a station | no | yes |
| Changing the server policy | no | yes |
| The audit log | no | yes |
| Managing accounts | no | yes |

The server makes the check on every request: the `require_admin` dependency works
on top of `require_operator`. The role is read from the operator's row, not from
the token, so a change applies to the person's very next action, with no new
sign-in and no session revocation. A refusal for lack of the role is a 403
(`Administrator role required`), not a 401: the session is fine, and the panel
can explain what is missing instead of throwing the person out to the sign-in
screen. Hiding a control in the panel is a courtesy, not protection. Two tests
keep this honest: one walks the OpenAPI schema and fails if any operation other
than sign-in, agent enrollment, and `/health` can be reached without credentials;
the other calls every operator operation with real administrator and observer
tokens and compares the outcome with the table above. The contract describes a
403 response on the administrator-only operations.

**Accounts.** All operations are `/api/v1/operators...`, administrators only.

- `GET` -- the list (`id`, `username`, `role`, `status`; no password hash).
- `POST` -- creation: a username (Latin letters, digits, and `. _ @ -`, up to 64
  characters, starting with a letter or digit), a role, and an initial password
  (at least the policy's minimum). Usernames are unique ignoring letter case; a
  repeat is a 409.
- `PATCH /{id}` -- a role and/or a status. One's own account cannot be changed
  (409): the calling administrator therefore always remains active, so the panel
  cannot leave the deployment without an administrator. Setting the value that is
  already there is a 200 with no audit entry. Disabling ends the account's
  sessions (`token_version` is raised) and forbids sign-in; a role change does
  not end sessions, because the role is read on every request.
- `POST /{id}/password` -- another administrator's reset: the password is
  replaced, the sessions end, and the account's login and password-change
  throttles are cleared so a person who was locked out can sign in with the new
  password. One's own password is not changed this way -- that is the form in
  "Настройки" (Settings), which asks for the current password.

Accounts are never deleted, only disabled: the names in the audit log should keep
pointing at someone. The log records `operator.created`, `operator.role_changed`
(from and to), `operator.disabled`, `operator.enabled`, and
`operator.password_reset`; a sign-in attempt on a disabled account is
`operator.login_failed` with the reason `disabled`. Neither passwords nor their
hashes reach the log or any response. On upgrade every existing account becomes
an administrator (the migration), so that nobody loses access; the `role` column
has no default, so an account without a stated role cannot be created. The
account from `WARDEN_SEED_ADMIN_*` is an administrator.

**The panel.** The panel takes the role from `GET /api/v1/auth/me`. The navigation
shows "Журнал" (audit log) and "Операторы" (operators) only to an administrator,
and the role is shown beside the name. An observer has no token-issuing button, no
window request form, and no "Станции" (stations) card in settings, and the
`/audit` and `/operators` screens opened by address show "Недостаточно прав для
просмотра этого раздела" (not enough rights to view this section). When the server
answers 403 to a request that carried a token, the API client calls a handler, the
panel reads the role again, and what is no longer allowed disappears for a person
whose role was lowered while a screen was open. While the role is unknown, nothing
that needs one is shown.

## Agent collectors

Each event category has a platform backend selected at runtime
(`warden_agent.collectors.registry`; constitution principle 1 -- all
OS-specific code stays inside a collector's own `linux.py`/`windows.py`):

| Category | Linux | Windows |
|---|---|---|
| Hardware and software | `psutil` (hardware) + `dpkg-query`/`rpm` (packages) | `psutil` (hardware) + the `...\Uninstall` registry key |
| Removable media | `/sys/block/*/removable` + `/proc/mounts`, no external tool | `pywin32`: `GetLogicalDriveStrings`/`GetDriveType` |
| Printing | CUPS `page_log` | Event ID 307 on the `PrintService/Operational` channel |
| Processes | `psutil.process_iter`, cross-platform | same |
| Websites | Chromium-family and Firefox history (a SQLite copy, since the live file is locked by the browser) | same |

The logic that turns raw data into events (parsing a `page_log` line, a
registry entry, diffing a set of devices) is pulled out into plain functions
and unit-tested on fixtures on any platform. The system calls themselves
(`winreg`, `pywin32`) are thin glue, verified live only where that was
actually possible (constitution Section VI and [usage.md](usage.md)).

## Boundaries

The full list is constitution Section V. The essentials:

- websites come only from browser history, not traffic interception;
- printing is only what goes through the system spooler, not straight to a
  device;
- a response to a request arrives after up to one poll interval, not
  instantly;
- browser history is visible only for the OS account the agent service runs
  as -- on a genuinely shared, multi-user machine this does not cover every
  account at once;
- one report is capped at 10,000 events, and an inventory snapshot at
  10,000 hardware entries and 10,000 software entries each; reading the
  daily event list or the change timeline returns at most 2,000 rows per
  call (500 by default), with `limit`/`offset` pagination -- comfortable
  headroom for real traffic (a window capped at 4h, polled once a minute),
  but rows past the page size need a follow-up request to see;
- the cross-station report reads only what is already on the server, and
  events get there solely through window requests (principle 2). It is not
  "everything the fleet did in the period": a station whose window was never
  requested shows nothing, however much happened on it;
- repeated requests for overlapping windows store the same event twice --
  there is no deduplication on ingestion, so the report (like the daily one)
  can show duplicates;
- only all of an operator's sessions can be ended at once: the operator does it
  by changing the password or with "Завершить все сеансы" (end all sessions), an
  administrator by disabling the account or resetting its password. A single
  session can be neither seen nor ended alone, and a stolen token works until one
  of those happens or the token expires (8 hours by default). The server does not
  detect a theft. A session issued before versions existed is refused once after
  the upgrade;
- an observer sees everything the complex has collected: the role removes the
  ability to act and to read the audit log, not the ability to read stations'
  data, and an observer cannot be limited to particular stations;
- an initial or reset password is known to the administrator who set it until the
  person changes it; nothing forces a change at first sign-in;
- two administrators acting on each other at the same instant can leave the
  system without an active administrator: the rule that nobody changes their own
  account guarantees a remaining administrator only while actions are
  sequential, and repairing that race needs direct access to the database;
- a policy change applies only from the next use: sessions, enrollment tokens, and
  window requests that already exist keep their own lifetime or limit, so shortening
  a session or a token lifetime ends nothing that is already out there;
- there is one policy for the whole deployment, and the audit log is its only
  history: no setting per operator or station, and no history screen or undo other
  than the reset to the configuration;
- a saved policy outranks the server's configuration until it is reset: after the
  first save, editing the configuration alone does not change these three values;
- the audit log is incomplete: it records changes and sign-ins, but not reads
  (reports, station lists, the log itself) and not the rejections a disabled
  station receives;
- the audit log is not protected against edits: it is "append-only" only in how
  the server code uses it. There is no trigger or permission restriction in the
  database, so anyone with write access to PostgreSQL can change or delete rows,
  and the panel will not show that;
- the actor of an entry has not always been verified: for a rejected
  registration (`agent.enroll_rejected`) it is the hostname sent by a caller who
  has no valid token at that point. The panel renders it as text, never as
  markup;
- a disabled agent keeps getting a 401 and logging it locally; the server does
  not audit these rejections. From the second consecutive failure on, the
  poll interval doubles on every further attempt, capped at 16 times the
  configured value (a 60-second interval backs off to at most 16 minutes), so
  a disabled station stops hammering the server forever while still noticing
  on its own once it is re-enabled, with no restart needed. A window request
  for a disabled station is rejected outright (409) instead of being queued
  until the station comes back.

## Answers to common questions

**Why not a WebSocket / a persistent connection?** It would give the
impression of an instant response, but would need Redis/pub-sub for routing
and reconnect handling -- disproportionate complexity for what this complex's
request volume actually needs (windows measured in hours, not seconds).

**Why can't the server just reach the agent directly?** A workstation almost
always sits behind NAT or an organization's firewall; an inbound connection
from the server to it is generally not workable. The active model (the agent
always comes to the server) works under those conditions without exception.

**What stops the agent from handing back an arbitrarily large period?**
Nothing, by itself -- which is exactly why the ≤4h check is duplicated: on
the server when a request is placed, and on the agent when it is carried
out. A defect in one half does not let the limit be bypassed.
