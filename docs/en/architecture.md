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
| `audit_log` | Every notable action: enrollment, task dispatch, login, configuration changes |

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

## Authentication

Two independent mechanisms (constitution principle 5):

- **Agents** — an `X-Agent-Key` header carrying the permanent key issued at
  enrollment. The server stores only its SHA-256 hash and compares it via
  `hmac.compare_digest` (constant-time). The key must match the specific
  `agent_id` named in the request path -- otherwise one agent's key would
  work against every other agent's endpoints.
- **Operators** (the panel) — a JWT issued on login
  (`POST /api/v1/auth/login`). Passwords are stored with Argon2id.

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
  account at once.

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
