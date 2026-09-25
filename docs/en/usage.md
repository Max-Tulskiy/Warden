# Deployment and usage guide

The canonical text is in Russian; see [../ru/usage.md](../ru/usage.md).

## Deploying the server

Requires Docker and Docker Compose.

```bash
cp .env.example .env
# edit .env: POSTGRES_PASSWORD, WARDEN_JWT_SECRET,
# WARDEN_SEED_ADMIN_USERNAME/PASSWORD, WARDEN_DOMAIN
docker compose up --build -d
```

What happens:

1. PostgreSQL starts and waits for its healthcheck.
2. The server applies Alembic migrations and starts; if
   `WARDEN_SEED_ADMIN_USERNAME`/`WARDEN_SEED_ADMIN_PASSWORD` are set and the
   database has no operator yet, a first administrator account is created.
3. The web panel is built and started.
4. Caddy obtains a (self-signed, for `localhost`) TLS certificate and proxies
   `/api/*` to the server, everything else to the panel.

The panel is reachable at `https://localhost/` (the browser will warn about
the self-signed certificate -- expected for a local/self-hosted deployment;
point `WARDEN_DOMAIN` at a real domain instead and Caddy will obtain a real
Let's Encrypt certificate automatically).

**Change the administrator password after first login** (panel → "Настройки"
(Settings) → "Смена пароля" (Change password); at least 12 characters) and
remove `WARDEN_SEED_ADMIN_USERNAME`/`WARDEN_SEED_ADMIN_PASSWORD` from `.env` -- the
bootstrap only creates an account when there is no operator at all yet, so a
later container restart with the same variables changes nothing, but there
is no reason to keep a production password sitting in `.env` in the clear
longer than needed.

## Enrolling an agent

1. Log in to the panel and issue an enrollment token (from the panel, or
   directly: `POST /api/v1/enrollment-tokens` with an
   `Authorization: Bearer <JWT>` header).
2. On the workstation, put that token in the agent config's
   `enrollment_token` field before the first start. Until that field is
   removed, the config carries a live one-time secret -- handle it like
   one. Packages install `/etc/warden-agent/config.toml` at mode `0600`
   inside a `0700` directory (Linux) and restrict the file to the
   SYSTEM/Administrators accounts (Windows, unverified -- no test
   machine).
3. Once enrolled, the agent saves its issued key to `state.json` -- the
   config's `enrollment_token` line must then be deleted by hand, it does
   not disappear on its own and is no longer needed.

## Working in the panel

**Reports.** The "Отчёты" (Reports) section shows the events of several
stations at once over a chosen period: "last hour", "last 24 hours", "last 7
days", or a custom one. You can narrow it to specific stations (none ticked
means all) and to a category. The report shows only events the stations
delivered in answer to window requests: to see a station's activity over the
period you care about, request a window for it (the station page, at most 4
hours per request). Repeated requests for overlapping windows can put
duplicates in the report -- there is no deduplication on ingestion.

**Settings.** Four blocks: changing your password (the current password is
required; after the change this session carries on and all the operator's other
sessions end -- their browsers return to the sign-in screen on the next action);
sessions (the "Завершить все сеансы" (End all sessions) button, with a
confirmation, signs you out of the panel on every device, this one included);
the server policy (an administrator changes three values, the rest is
read-only -- see below); and the list of stations. The whole set of an operator's sessions
always ends together; a single session cannot be chosen. After the server is
upgraded to a version with session ending, each operator signs in once again:
tokens issued earlier carry no version and are refused.

**Server policy.** In "Настройки" (Settings) an administrator changes three values: the
longest request window for a station (1 to 4 hours), the lifetime of an enrollment token
(1 to 168 hours), and the lifetime of a session (5 minutes to 24 hours). Beside each
field are its allowed range and the default from the server's configuration. The window
can never exceed 4 hours, whatever is set: it is a ceiling, not a parameter. "Сохранить"
(Save) writes all three values; the new window limit applies to the next requests, the
session length to new sign-ins, and the token lifetime to new tokens, while sessions,
tokens, and requests already issued keep their own lifetime. Once a policy is saved a
"Сбросить к значениям сервера" (Reset to the server's values) button appears (with a
confirmation): it deletes the saved set, and the configuration applies again.
**Important:** while a policy is saved, the server variables
`WARDEN_MAX_REQUEST_WINDOW_HOURS`, `WARDEN_ENROLLMENT_TOKEN_TTL_HOURS`, and
`WARDEN_JWT_EXPIRE_MINUTES` are only defaults, and editing them changes nothing until
the policy is reset. (The shipped `docker-compose.yml` does not forward these three from
`.env`: to change the defaults, add them to the `environment` of the `server` service.) The form that
requests a station's data shows the window limit in force. An observer sees the same
values but cannot change them. The other limits (upload size, page size, minimum
password length) are set by the configuration and cannot be changed from the panel. Who
changed the policy, and when, is in the "Журнал" (audit log), group "Изменения политики"
(policy changes).

**Disabling a station.** The "Отключить" (Disable) button in the stations
block (with a confirmation) blocks the agent's key: on its next contact it
gets a 401. The station's events and inventory are kept. "Включить" (Enable)
puts the station back to work with the same key, no new enrollment. A
disabled station's agent keeps polling the server and writing 401 errors to
its own log -- that is expected; the server does not log these rejections.

**Audit log.** The "Журнал" (audit log) screen shows audit log entries for the
chosen period ("Последний час" (last hour), "Последние 24 часа" (last 24 hours),
"Последние 7 дней" (last 7 days), or a custom one), newest first: the time, the
action, who performed it, what it was performed on, and the details. Actions are
shown under Russian names; a code with no name is shown as it is. Entries can
be narrowed by actor (an operator's username, a station id, or a hostname --
matched exactly) and by action: one specific action or a group, for example "Все
действия операторов" (all operator actions). To check whether someone is guessing
the password, choose "Неудачный вход оператора" (failed operator login). A station
id is shown as the station's hostname when the station list has loaded. If more
entries match than fit on a page, "Показать ещё" (show more) loads the next ones.
The log records changes and sign-ins, but not reads and not the rejections a
disabled station receives, and anyone with database access can alter its
entries -- the hint under the filters says the same.

**Operators and roles.** Every account has one of two roles. An **administrator**
can do everything: request data from stations, issue enrollment tokens, enable and
disable stations, read the audit log, and manage accounts. An **observer** sees
stations, reports, inventory changes, and the server policy, changes their own
password and ends their own sessions, but does nothing to stations, does not read
the log, and does not manage accounts; those sections and buttons are absent from
an observer's panel, and a direct request is refused by the server (403). The
"Операторы" (Operators) section, for administrators only, lists every account with
its role and status and lets you create an account (a name of Latin letters,
digits, and `. _ @ -`, a role, and an initial password), change a role, disable and
enable an account, and reset a password. Disabling and a password reset end that
account's sessions, and a role change applies to the person's very next action.
Your own account cannot be changed, so an administrator cannot disable or demote
themselves; accounts are never deleted, only disabled. An initial or reset
password is known to the administrator who set it until the person changes it in
"Настройки" (Settings), so ask them to change it at first sign-in. The account from
`WARDEN_SEED_ADMIN_*` is the first administrator: create personal accounts from it
and, once they exist, remove its password from `.env`. An observer sees all the
collected data of all stations -- they cannot be limited to particular stations.

## Installing the agent

### Windows 10/11 (`.msi`)

Download the `.msi` from the release page and run it as an administrator. It
installs the "Warden Insider-Activity Monitoring Agent" service (auto-start)
and a default configuration at
`%ProgramData%\Warden\agent\config.toml` -- edit it (server address,
enrollment token) and restart the service:

```powershell
Restart-Service WardenAgent
```

The agent keeps its event buffer (`buffer.db`) and its state with the
agent key (`state.json`) in the same `%ProgramData%\Warden\agent`
directory. The installer locks that directory down: only SYSTEM and
Administrators have access, so ordinary users can read neither the config
with its enrollment token nor the agent key. The rights are set by
well-known SID, so the installation does not depend on the Windows
language. Uninstalling the agent leaves these files in place -- remove the
directory by hand if it is no longer needed.

> The installer is unsigned -- SmartScreen will warn on first run
> (constitution Section V).

### Linux (`.deb` / `.rpm`)

```bash
# Debian/Ubuntu
sudo dpkg -i warden-agent_<version>_amd64.deb

# Fedora/RHEL and derivatives (ALT included)
sudo rpm -i warden-agent-<version>.x86_64.rpm
```

Both packages place the config at `/etc/warden-agent/config.toml` along with
a systemd unit. Edit the config, then enable the service:

```bash
sudo systemctl enable --now warden-agent
```

### From source (`pip`)

```bash
cd agent
pip install -e ".[dev]"
python -m warden_agent --config ./config.example.toml
```

## Verification without real hardware

Per constitution principle 7, server logic and the agent buffer are checked
by unit and integration tests with no flash drive, printer, or elevated
privileges needed:

```bash
cd server && pytest         # a test database (SQLite), no real PostgreSQL needed
cd agent && pytest          # buffer on a temp file, collectors against fixtures
cd web && npm test
```

A separate CI job (`server-postgres-smoke` in `ci.yml`) runs migrations and a
server startup against a real PostgreSQL instance -- this has also been
checked by hand: the full cycle (`docker compose up` → log in → issue a
token → enroll an agent → the station shows up in the list) was run end to
end against the real stack while preparing this release.

## Honest status of live platform-collector verification

Constitution Section VI requires more than passing unit tests -- at least one
live check of platform-specific code on a real system. As of this release:

| Platform | What has been checked live |
|---|---|
| Linux | All five collectors, on the development machine: real `dpkg`/`psutil` data (inventory), a real subprocess and a real `psutil`-observed process (processes), temporary SQLite files matching the Chrome/Firefox schema (websites). The full `.deb`/`.rpm` build via `nfpm` from an actually-frozen PyInstaller binary was run and the packages' contents inspected. |
| Windows | **Not checked live** -- there is no Windows machine on the development side. The code is written against the documented APIs (`pywin32`, `winreg`, `win32evtlog`) and type-checked; all of the *parsing logic* (`parse_uninstall_entries`, `parse_print_event_xml`, the device diff) is unit-tested on fixtures on any platform. CI (`ci.yml`, the `agent-test` job) genuinely runs the `test_*_windows_live.py` tests on a `windows-latest` runner -- the first real exercise of the `pywin32`/`winreg` calls, not just a code read-through. The `.msi` build (`release.yml`) is likewise built for real only in CI, on the first tag push, not verified locally beforehand. |

Disabling a station (see "Working in the panel") is covered by an end-to-end
integration test: the agent's real `ServerClient` and `run_poll_pass` against
the real server app -- a 401 after the station is disabled, with no retries,
and recovery once it is re-enabled. The behavior of a disabled agent on a
real Linux or Windows workstation has **not** been checked.

The "Отчёты" (Reports) and "Настройки" (Settings) screens were additionally
walked through by hand on the real stack (`docker compose`: Caddy +
PostgreSQL, a separate project with clean volumes): login; a password change
(wrong current password -- 400, too-short new one -- 422, success -- the new
password logs in and the old one is refused); two "agents" delivering
windows; the cross-station report (station and category filters, a week-long
range, paging, a reversed range -- 422); disabling and re-enabling a station
(a disabled station's poll, report, and inventory calls get a 401 -- the same
response as a wrong key; after re-enabling the same key works again); the
`audit_log` rows, and no passwords in it. The `ix_events_occurred_at`
migration was applied, reversed, and applied again on PostgreSQL over the
previous revision's schema. Both screens were opened in a real browser
(Chromium driven by Playwright). What this does **not** prove: the "agents"
were HTTP calls from a script, not the agent service on Linux or Windows; the
index was checked on three rows (the planner uses it once sequential scans
are disabled), not on a large table; and there was only one browser --
Chromium.

The "Журнал" (audit log) screen was walked through by hand on a real stack
(`docker compose`: Caddy + PostgreSQL 16, a separate project with fresh volumes,
the proxy on non-standard ports). Entries were created by real calls: a failed and
a successful login, an enrollment token, two station enrollments, a rejected
enrollment whose hostname was `<img src=x onerror=alert(1)>`, a station disabled
and re-enabled, and two inventory uploads with a change. Checked: reading through
the proxy; newest-first order; the `operator` group and the exact code
`operator.login` (without `operator.login_failed`); a partial code returning
nothing; an actor combined with a group; a station id as the actor; paging with no
gaps or repeats; 422 for a reversed range and for `%` in the action; 401 without a
token; a 30-day range; and no new entries after reading the log. With 600 rejected
logins the first page is exactly 500 rows, "Показать ещё" loads the rest with no
repeats, and the button then disappears. In a real browser (Chromium driven by
Playwright): a hostname is shown instead of a station id, the `<img ...>` text is
shown literally and creates no element, the hint about the log's limits is in
place, and there were no console errors. The migration of the
`ix_audit_log_occurred_at` index was applied, reverted, and applied again on
PostgreSQL. What this does **not** prove: the "stations" were HTTP calls from a
script, not the agent service on Linux or Windows; the index was checked on a few
hundred rows, and that period queries actually use it was not verified (the query
plan was not examined); and there was only one browser -- Chromium.

Ending sessions was walked through by hand on a real stack (`docker compose`:
Caddy + PostgreSQL 16, a separate project with fresh volumes, the proxy on
non-standard ports): through the proxy, and in two independent Chromium contexts
driven by Playwright that stand for two browsers of one operator. Checked: the
token carries `ver`; a wrong current password (400) and a too-short new one (422)
end nothing; a successful password change answers 200 with a token whose version
is one higher, the other session and the old token of the session that made the
change get a 401 (the same response as for an invalid token), the returned token
works, and the old password no longer signs in; a token with no `ver` is refused;
`logout-all` gives a 401 without a token and a 204 with one, after which every
session is refused, a second call gives a 401, and a new sign-in works; the audit
log holds `operator.password_change` and `operator.sessions_revoked` and no
passwords or tokens. In the browser: after a password change the first browser
stays signed in and stores the new token, the second returns to the sign-in
screen on its next action with the message "Сеанс завершён. Войдите снова."
(the session has ended, sign in again) and clears its stored token, and after it
signs in again the message is gone; "Завершить все сеансы" (end all sessions)
asks for confirmation first, "Отмена" (cancel) sends nothing, confirming leads to
the sign-in screen without the refusal message (it is a deliberate sign-out), and
the second browser does get the message. The audit screen shows the new actions
under their Russian names. The `token_version` migration was applied, reverted,
and applied again on PostgreSQL, and an operator created before it read version
0. What this does **not** prove: behavior with several server processes (the
counter lives in the database, so it should hold, but there was one process);
simultaneous password changes under load were not tested, and a single SQL
statement is the guarantee; and there was only one browser -- Chromium.

Roles and account management were walked through by hand on a real stack (`docker
compose`: Caddy + PostgreSQL 16, a separate project with fresh volumes, the proxy on
non-standard ports): through the proxy, and in two independent Chromium contexts
driven by Playwright that stand for an administrator and an observer at the same
time. Through the proxy: an administrator creates an observer, who signs in, and
`/auth/me` names the roles; the observer gets 200 on stations, the policy, and a
report, and 403 (`Administrator role required`) on issuing a token, disabling a
station, requesting a window, the audit log, and all four account operations,
while without a token every one of them gives 401; a promotion and a demotion apply
to the same token from the next request, and a demoted session still works for an
observer's actions; a case-variant duplicate name is 409, and a bad name, a short
password, and an unknown role are 422; disabling ends the session and closes
sign-in with the same response as a wrong password, and enabling does not bring
the session back; a password reset replaces the password and ends the sessions;
changing one's own role, status, and password is 409; one administrator disables
another and the other is refused, while the last administrator cannot disable
themselves; the audit log holds all five new actions, a role change records "from"
and "to", a sign-in on a disabled account is marked with the reason `disabled`, and
no password or token is in the log. In the browser: an observer has no "Журнал" or
"Операторы" item, no token-issuing button, and no "Станции" card in settings, and
`/audit` and `/operators` opened by address show "Недостаточно прав для просмотра
этого раздела" without signing them out; a direct request with their token gets
403; an administrator creates an account through the form, promotes and demotes a
role, disables with a confirmation and enables, and resets a password (a
mismatched repeat is refused); when a role is lowered while an observer has the
administrator panel open, their next action shows the same notice and the items
disappear while the session stays; a disabled person's open browser shows the
sign-in screen with "Сеанс завершён. Войдите снова."; and the audit screen shows the
new actions under Russian names. The roles migration was applied, reverted, and
applied again on PostgreSQL: an operator that existed before it became
`ADMIN`/`ACTIVE`, `role` has no default, an insert without a role is refused, and
`alembic check` is clean. What this does **not** prove: the race of two
administrators disabling each other at the same instant (it is named as a boundary
and was not reproduced); behavior with several server processes; and there was
only one browser -- Chromium.

The editable policy was walked through by hand on a real stack (`docker compose`: Caddy
+ PostgreSQL 16, a separate project with fresh volumes, the proxy on non-standard
ports): through the proxy, and in two independent Chromium contexts driven by Playwright
that stand for an administrator and an observer at the same time. Through the proxy:
before the first save the configuration's values are in force, `overridden` is false,
and `defaults` and `bounds` match the fixed ranges; an observer reads the policy and
gets 403 on `PUT` and `DELETE`, and without a token both give 401; ten bad bodies (a
window of 5 and 0, a token of 169, a session of 4 and 1441, a fraction, a string, a
boolean, a missing value, an extra field) give 422 and store nothing; after saving 2 h /
2 h / 30 min, a 3-hour window is refused naming the limit and a 2-hour one is accepted,
a new enrollment token lives 2 hours, a new sign-in gets a 30-minute session, and a
session issued before the change keeps working and keeps its 8-hour expiry; saving the
same values again adds nothing to the audit log; the log holds one `policy.changed` with
the old and new values and the `overridden` marker and, after a reset, one `policy.reset`
with the values it went back to, a second reset writes nothing, and no secret is in the
entries; a 5-hour window is refused even with nothing saved (the ceiling). Separately:
after saving 3 h / 6 h / 45 min the server's configuration was changed (session 15
minutes, window 6 hours, token 48 hours) and the server container recreated, and the
saved values stayed in force while `defaults` showed the new configuration, the 6-hour
window clamped to 4; after a reset the new values applied (window 4, token 48, session
15), a new sign-in gave 15 minutes, and a 5-hour window was still refused. In the
browser: an administrator sees three fields with values, units, ranges, and defaults,
and before a save a note that the configuration decides and no reset button; a window
of 5 is refused on screen naming the range; a save says what applies when, announces
the saved policy, and reveals the reset button; the station's data-request form names
the limit in force (2 hours), refuses a 3-hour window before sending and accepts a
2-hour one; an observer sees the saved values as rows with no fields or buttons and a
note that only administrators can change them; the reset first asks, naming the values
it returns to, "Отмена" (cancel) changes nothing, and confirming returns the
configuration; and the audit screen shows both actions under Russian names in the
"Изменения политики" (policy changes) group. The migration was applied, reverted, and
applied again on PostgreSQL: the table is created empty, a second row is refused by the
check, and `alembic check` is clean. What this does **not** prove: two administrators
saving for the first time at the same instant (only a unit test that simulates the
failed insert covers that race); behavior with several server processes (reading at
every use should provide it, but there was one process); and there was only one
browser -- Chromium.

This is not an oversight -- it follows directly from constitution principle
10 ("honesty about boundaries"): naming the actual level of confidence beats
leaving the impression that both platforms were checked equally.
