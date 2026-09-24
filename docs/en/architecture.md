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
| `operators` | Panel administrator accounts |
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

**The server policy** (`GET /api/v1/policy`) is read-only: the request-window
cap, the lifetime of an enrollment token and of a session, the minimum
password length, and the limits on an agent report, an inventory snapshot,
and a page of results. Each value is read from where it is actually enforced,
and the response is an explicit list of fields rather than a dump of the
settings, so a secret (`jwt_secret`, the database connection string) cannot
reach it by accident. These values cannot be changed from the panel -- only
through the server's configuration.

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
login. The passwords themselves never reach the log. Changing the password
does **not** revoke sessions already issued: a JWT is self-contained and stays
valid until it expires (`jwt_expire_minutes`, 8 hours by default) -- a
limitation, not a solved problem. The seed account from `WARDEN_SEED_ADMIN_*`
is created only when the operators table is empty, so restarting the
container does not bring the old password back.

All external traffic runs over TLS, terminated at the Caddy reverse proxy
(`docker-compose.yml`, `Caddyfile`), not by the application server itself.

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
- changing the password does not end sessions already issued: a stolen token
  works until it expires (8 hours by default);
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
- a disabled agent keeps contacting the server once per poll interval and
  getting a 401, logging the error locally; the server does not audit these
  rejections (that would be about 1,440 rows a day per station). A window
  request can still be placed for a disabled station: it stays queued until
  the station is re-enabled, after which the agent answers from a buffer that
  has already been partly pruned.

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
