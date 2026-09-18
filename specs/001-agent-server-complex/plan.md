# Implementation plan: Agent-server complex

**Spec:** [./spec.md](./spec.md) · **Status:** draft · **Date:** 2026-09-15

---

## 1. Approach

A system of three modules, connected only through the API contract
(`contracts/openapi.yaml`):

**`server/`** (FastAPI + PostgreSQL) — accepts agent enrollment, places and
hands out tasks, ingests data and snapshots, keeps reports, detects
configuration changes, and serves the web panel.

**`agent/`** (`warden_agent`, an installable Python module) — runs as a
service (systemd on Linux, a Windows service). Active-agent model
(constitution D-1): it listens for nothing and initiates all HTTPS requests
to the server itself.

* `warden_agent.core.scheduler` — three independent loops: collection
  (collectors write to the buffer continuously), task polling (every
  `poll_interval`, 60s by default), inventory/heartbeat (every
  `inventory_interval`, 1h by default).
* `warden_agent.core.transport` — an HTTP client (`httpx`) carrying the
  per-agent key in a header, with exponential-backoff retry on network
  errors.
* `warden_agent.buffer.Buffer` — a thin wrapper over SQLite: `add_event`,
  `events_in_window(category, start, end)`, `prune(older_than)`.
* `warden_agent.collectors.base.Collector` — a protocol with a `collect()`
  method returning a list of events; a per-category registry;
  `warden_agent.collectors.registry.for_platform()` picks the platform
  backend.

**`web/`** (React + TypeScript + Vite) — an administrator panel on top of the
server's API.

The "window request" flow (R-6, R-7, A-2…A-4):
`POST /api/v1/agents/{id}/requests` (operator, window ≤4h, validated by
`WindowRequestIn`) → a row in the `tasks` table with status `pending` → the
agent picks it up on its next `GET /api/v1/agents/{id}/tasks` → the agent
re-checks the ≤4h window (principle 3 — checked twice) → selects events from
the buffer → `POST /api/v1/agents/{id}/reports` with `task_id` → the server
stores the events and marks the task `completed`.

The inventory flow (R-10, R-11, A-6, A-7): the agent periodically sends
`POST /api/v1/agents/{id}/inventory` with a canonical JSON payload (sorted
keys) and its SHA-256 hash; `warden_server.services.inventory.detect_changes`
compares that hash against the station's last saved snapshot; on a match, only
`last_seen` is updated; on a mismatch, a new snapshot is stored plus a row in
`inventory_changes` carrying a diff (added/removed/modified, by top-level key
under `hardware`/`software`).

## 2. Alternatives considered

| Option | Why rejected |
|---|---|
| A single combined agent+server module | The assignment describes a client-server application with different runtime environments (server on Docker/Linux, agent on a Windows/Linux workstation); separate modules with a contract between them let each be versioned and shipped independently |
| Flask instead of FastAPI | FastAPI gives request validation via Pydantic and OpenAPI generation for free — the contract (principle 11) would otherwise have to be maintained by hand |
| Store agent events directly in the shared database, no local buffer | Contradicts the active-agent model (D-1): an agent behind NAT is unreachable for a server-initiated push, so it must accumulate data locally until the next poll |
| Check the ≤4h window only on the server | A server defect (or a direct call to the agent bypassing it) would let an arbitrary amount of data leak out — principle 3 requires the check on both sides |

## 3. Constitution compliance

| Principle | How it is satisfied |
|---|---|
| 1. Platform code is isolated | Collectors: `warden_agent/collectors/<category>/linux.py` and `.../windows.py`; `warden_agent.core` and `warden_agent.buffer` import neither `winreg` nor `pyudev` |
| 2. Data does not leave the buffer without a request | `transport.push_report` is only called from the `window_request` task handler; the periodic collection loop only writes to `Buffer`, never sends anything |
| 3. Window ≤ 4 hours | `WindowRequestIn.validate_range` on the server (a Pydantic validator) and `TaskHandler.validate_window` on the agent — the same bound, checked in two independent places |
| 4. Buffer retention is bounded | `Buffer.prune` runs before every pass of the collection loop; `retention_hours` in the config, 8 by default, checked to be at least 4 when the config loads |
| 5. Exchange is authenticated and encrypted | Agent endpoints require an `X-Agent-Key` header, verified against a hash (`argon2`); operator endpoints use JWT (`warden_server.api.deps.require_operator`); TLS terminates at the reverse proxy in front of the server (docker-compose) |
| 6. Inventory is versioned separately | `inventory_snapshots` (append-only) + `inventory_changes`; see the inventory flow above |
| 7. Logic is testable without hardware | `Buffer` unit tests run against a temporary SQLite file; Linux collector unit tests run against fixtures (sample `dpkg -l` output, a sample `page_log` line); server integration tests run against a test database (`testcontainers`/in-memory SQLite for CI) |
| 8. Every action is logged | `warden_server.services.audit.log_event` is called from every endpoint handler; the agent logs to a local file via the standard `logging` module |
| 9. Language mode | Code/docstrings in English; API error text and the panel's interface in Russian |
| 10. Honesty about boundaries | `docs/ru/architecture.md` carries a boundaries section that matches constitution Section V word for word |
| 11. The API contract is the single source of truth | `contracts/openapi.yaml` describes every endpoint in this plan; `schemathesis` checks it against a running server in CI |

**Violations:** none.

## 4. Affected modules

| Module | Change |
|---|---|
| `server/src/warden_server/models/` | New: `agents`, `enrollment_tokens`, `tasks`, `events` (per category), `inventory_snapshots`, `inventory_changes`, `operators`, `audit_log` |
| `server/src/warden_server/schemas/` | Pydantic request/response schemas matching `contracts/openapi.yaml` |
| `server/src/warden_server/api/` | Routers: `agents.py` (enroll/tasks/reports/inventory), `requests.py` (operator places a request), `auth.py`, `reports.py` (reads for the panel) |
| `server/src/warden_server/services/` | `tasks.py` (dispatch), `inventory.py` (change detector), `audit.py` |
| `server/alembic/` | Initial schema migration |
| `agent/src/warden_agent/core/` | `config.py`, `scheduler.py`, `transport.py` |
| `agent/src/warden_agent/buffer/` | `store.py` (SQLite) |
| `agent/src/warden_agent/collectors/` | `base.py`, `registry.py`, categories `inventory/`, `removable_media/`, `printing/`, `processes/`, `web/`, each with `linux.py` (working implementation) and `windows.py` (implementation behind a platform check — live verification is Section VI's concern, not CI's) |
| `agent/src/warden_agent/service/` | Entry points: `linux.py` (systemd), `windows.py` (service wrapper via `pywin32`) |
| `web/src/` | Screens: station list, station detail, window-request form, event view, configuration-change timeline, login |
| `contracts/openapi.yaml` | Contract for every endpoint above |

## 5. Data formats

Core server tables (PostgreSQL, `JSONB` for event payloads):

* `agents(id, hostname, os, agent_key_hash, status, enrolled_at, last_seen_at)`
* `enrollment_tokens(token_hash, created_by, expires_at, used_at)`
* `tasks(id, agent_id, kind, window_start, window_end, status, created_by, created_at, completed_at)`
* `events(id, agent_id, task_id, category, occurred_at, payload JSONB)` — categories: `removable_media`, `printing`, `processes`, `web`
* `inventory_snapshots(id, agent_id, collected_at, hardware JSONB, software JSONB, content_hash)`
* `inventory_changes(id, agent_id, detected_at, added JSONB, removed JSONB, modified JSONB)`
* `operators(id, username, password_hash)`
* `audit_log(id, actor, action, target, occurred_at, detail JSONB)`

Full request/response schemas live in `contracts/openapi.yaml`, grown together
with the endpoints (the contract and the implementation change in the same
commit, principle 11).

## 6. Interface

* Station list: hostname, OS, status (online/offline from `last_seen_at`), and
  an enrollment-token action for adding a new workstation.
* Request form: start/end pickers with a client-side ≤4h check (mirrors, does
  not replace, the server check).
* Station event view, tabbed by category, for the selected day's report.
* Configuration-change timeline: `inventory_changes` entries with an
  expandable diff.
* Operator login form.

## 7. Risks

| Risk | Mitigation |
|---|---|
| Windows collectors are written but not verified live (no Windows machine on the development side) | Fixture-based unit tests run in CI (`windows-latest` in the agent's test matrix); live verification is an explicit, separate `tasks.md` item, not a hidden part of "done" |
| Pydantic schemas drift out of sync with `contracts/openapi.yaml` | The contract is checked in CI (`schemathesis`), not written from memory and trusted |
| The per-agent key leaks into a log | The key is never logged — the audit log records `agent_id`, not the request header; a test asserts the logger's output never contains it |
| The agent's buffer grows unbounded during a long network outage | `retention_hours` bounds it; past that, old events are dropped rather than the file growing forever (a deliberate boundary, Section V) |

## 8. Verification plan

```bash
# server — no real agent, a test database
cd server && pytest tests/unit tests/integration

# agent — no real hardware, buffer on a temp file, collectors against fixtures
cd agent && pytest tests/unit tests/integration

# contract — against a locally running server
schemathesis run contracts/openapi.yaml --base-url http://localhost:8000
```

Live verification of platform collectors (Linux — available on the
development machine; Windows — only through the `windows-latest` CI matrix
leg, with no run on a physical station as of this plan) is tracked as a
separate, not-CI-automated task in `tasks.md`, and its honest status is
recorded in `docs/ru/usage.md`.
