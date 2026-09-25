# Warden Project Constitution

**Version:** 1.3.1 · **Adopted:** 2026-09-15 · **Last amended:** 2026-09-25

This document defines the project's purpose, mandatory development principles,
its structure, and the decisions already made. The constitution takes priority
over any other agreement: a spec, plan, or piece of code that contradicts it
must be fixed, or the constitution must be amended through the procedure in
Section VII.

---

## Purpose

Warden is a workstation-monitoring complex for an information-security
administrator, built to counter insider activity inside a protected perimeter.
An agent running on each workstation collects information about the station's
state; a server centrally displays it and keeps daily reports.

### Lab assignment functions

The project must observe five categories of information and handle server-side
requests for it. Each function is pinned to a specific module, and that mapping
cannot be broken without amending the constitution:

| Assignment function | Where it is implemented |
|---|---|
| Workstation hardware and installed software | `agent.collectors.inventory` (platform backends) → `server` (snapshots, change detector) |
| Removable media being connected | `agent.collectors.removable_media` |
| Documents sent to print | `agent.collectors.printing` |
| Running processes | `agent.collectors.processes` |
| Websites being opened | `agent.collectors.web` |
| Providing data for a requested window (no more than 4 hours) | `agent.core` (buffer, task handling) + `server` (request placement, ingestion) |
| Displaying data and keeping daily reports | `server` + web panel |
| Keeping hardware/software records separately, to detect configuration changes | `server` (`inventory_snapshots`, `inventory_changes`) |

---

## I. Principles

Principles are mandatory. Each is phrased so compliance can be checked when
reviewing a plan or a diff.

### 1. Platform-dependent code is isolated

Anything that depends on a specific operating system — enumerating media,
reading the print log, inventorying hardware and software, extracting browser
history — lives only in a collector's platform backend module
(`agent/src/warden_agent/collectors/<category>/<platform>.py`) and is selected
at runtime for the current platform. The agent core (`agent.core`,
`agent.buffer`) and the entire server codebase contain no OS branching and
import no platform-specific libraries.

*Check:* `agent.core`, `agent.buffer`, and `server` do not import `winreg`,
`pyudev`, `ctypes.windll`, or similar; grepping for `sys.platform` /
`platform.system` outside collector backend modules finds nothing.

*Why:* porting to a new platform must reduce to a new collector backend, not to
changes in the buffer, transport, or server.

### 2. Data does not leave the buffer without a request

The agent never sends collected events on its own initiative. The only reason
to transmit process, media, print, or web events is a `window_request` task
placed by the server. Inventory and heartbeat are the exception covered by
Section III (D-4): they are sent on a schedule, because they are needed to
detect configuration changes and to track liveness.

*Check:* the agent's transport sends category events only from the
`window_request` task handler; a code search finds no event push from the
collection scheduler.

*Why:* this is the active-agent model (D-1) and a direct consequence of the
assignment's own wording, "on request from the server."

### 3. A request window is capped at four hours

A data request specifies a time window of no more than 4 hours. The limit is
checked on both sides: the server refuses to place a request with a window
larger than 4 hours, and the agent refuses to serve a task whose window
exceeds the limit.

*Check:* a server unit test confirms rejection at a 4-hour-1-minute window; an
agent test confirms rejection of processing such a task.

*Why:* a literal requirement of the assignment. Checking it twice means a
defect on one side does not let an arbitrary amount of history leak out.

### 4. Local buffer retention is bounded

The agent's local buffer (SQLite) keeps events no longer than the configured
retention period (8 hours by default, never less than 4 — the request-window
cap). Stale records are pruned by the scheduler, not left to accumulate
forever.

*Check:* a buffer test confirms a record older than the retention period is
removed by the prune operation and does not appear in a window query.

*Why:* a monitoring agent must not turn into an indefinite surveillance
archive on the workstation. Keeping exactly as much as can ever be requested
is enough.

### 5. Agent-server exchange is authenticated and encrypted

The agent enrolls with a one-time enrollment token and receives a permanent
per-agent key. Every agent request carries that key; the server stores only
its hash. Operator-facing panel endpoints use a separate authentication
mechanism (JWT). Transport is TLS; plain HTTP is acceptable only inside a
development network behind a reverse proxy.

*Check:* agent and operator endpoints reject a request without a valid
credential; the database contains no column holding an agent key in the
clear.

*Why:* the complex collects sensitive workstation data — unauthenticated
access to it is itself a leak channel.

### 6. Inventory is versioned; changes are recorded separately

A hardware/software snapshot is stored together with a hash of its canonical
form. When a new snapshot arrives, the server compares its hash against the
previous one and, on a mismatch, records a separate change entry (added /
removed / modified) without overwriting snapshot history.

*Check:* a server test confirms a repeated identical snapshot creates no
change record, while a changed one creates one with a correctly parsed diff.

*Why:* the assignment's goal is detecting configuration changes, not just
storing the latest state.

### 7. Logic is testable without real hardware

Server logic and the agent buffer require no physical devices for tests: the
buffer works against a temporary database file, the server against a test
database. Collector platform backends are checked against fixtures (sample
`dpkg` output, a sample CUPS log line, a browser history file), not against a
live device in CI.

*Check:* `pytest` in `server/` and `agent/` passes in CI without a flash
drive, a printer, or elevated privileges.

*Why:* tests run on every commit precisely because they need no hardware.
Live verification of platform collectors is a separate manual step
(Section VI), not a condition for CI to pass.

### 8. Every action is logged

Agent enrollment, task pickup, window delivery, snapshot ingestion,
configuration-change detection, operator login, request placement, and
errors are all recorded in a log — centrally on the server, locally on the
agent.

*Check:* a new user or agent action adds a log entry; a code search finds a
logging call at every endpoint.

*Why:* a security-administrator workstation must itself be accountable — who
requested what, and when.

### 9. Language mode

* Identifiers follow their language's convention: `snake_case` in Python,
  `camelCase`/`PascalCase` in TypeScript.
* Code comments and docstrings — **English**.
* User-interface text and error messages shown to the administrator —
  **Russian** (the product is used and defended in Russian).
* Project documentation (`docs/`, `README.md`) — **Russian canonical**, with an
  **English** translation kept in sync (`docs/en/`).
* Spec-kit artifacts — this constitution, `.specify/templates/`,
  `.claude/commands/`, and everything under `specs/` — **English**.

*Why:* the product surface (interface, docs) targets a Russian-speaking
audience defending the lab; the engineering process artifacts (constitution,
specs, commands) stay in English so the development workflow itself reads
like an ordinary English-language engineering repository.

### 10. Honesty about boundaries

Documentation must plainly state what the complex does not collect and does
not guarantee, and where observation coverage differs across platforms. A
monitoring claim not backed by code or a test is a defect of the same class
as a bug.

*Example:* website collection relies on browser history and does not see
traffic in incognito mode or in a browser with a non-standard profile; this
is stated in Section V, not smoothed over by "the agent tracks visited
sites."

*Why:* a security workstation that overstates its own coverage is more
dangerous than an honest one — the administrator builds decisions on what the
system is believed to see.

### 11. The API contract is the single source of truth

The server's external contract is described in `contracts/openapi.yaml`.
Server request/response schemas and agent models conform to this document;
any divergence between the contract and the implementation is a defect. The
contract is checked in CI (schema lint and contract tests against a running
server).

*Check:* `schemathesis` against a running server finds no divergence from
`contracts/openapi.yaml`.

*Why:* the agent and the server are developed and shipped as separate
modules; the shared contract is the only thing that keeps them compatible.

---

## II. Project structure

```
LR3/
├── .specify/memory/constitution.md      this constitution (highest priority)
├── .specify/templates/                  spec / plan / tasks templates
├── .claude/commands/                    spec-driven workflow commands
├── specs/NNN-name/                      feature specifications (Section IV)
├── contracts/openapi.yaml               API contract — source of truth (principle 11)
├── server/                              server: FastAPI, PostgreSQL (src-layout)
├── agent/                               agent: distributable Python module (src-layout)
├── web/                                 web panel: React + TypeScript + Vite
├── packaging/
│   ├── windows/                         WiX — .msi installer, Windows service setup
│   └── nfpm/                            nfpm — builds .deb and .rpm, systemd unit
├── docker-compose.yml                   server deployment (server + postgres + web + proxy)
├── docs/ru/ (canonical), docs/en/ (translation)  architecture and usage docs
└── .github/workflows/                   ci.yml, release.yml, security.yml
```

Dependencies point strictly inward. `agent.core` and `agent.buffer` know
nothing about platform backends — those register through the shared
`Collector` interface. The server knows nothing about the agent's internals;
only the API contract connects them.

### Agent modules

| Module | Responsibility |
|---|---|
| `warden_agent.core` | Configuration, scheduler, transport (enroll / poll tasks / push / heartbeat), retry with backoff |
| `warden_agent.buffer` | Local event buffer (SQLite), window queries, retention pruning |
| `warden_agent.collectors` | Base `Collector`; categories `inventory`, `removable_media`, `printing`, `processes`, `web`; platform backends selected at runtime |
| `warden_agent.service` | Service entry points: `systemd` on Linux, a Windows service |

### Server modules

| Module | Responsibility |
|---|---|
| `warden_server.api` | Agent-facing and operator-facing endpoints, authentication |
| `warden_server.models` | SQLAlchemy models: agents, tokens, tasks, events, inventory, operators, audit log |
| `warden_server.schemas` | Pydantic schemas — match `contracts/openapi.yaml` |
| `warden_server.services` | Task placement/dispatch, configuration-change detector, daily aggregation |

### Workstation-side data

The agent's buffer and configuration live in an OS-specific directory:
`/var/lib/warden-agent` and `/etc/warden-agent/config.toml` on Linux;
`%ProgramData%\Warden\agent` and `%ProgramData%\Warden\agent\config.toml` on
Windows.

---

## III. Decisions

Decisions are recorded together with their rationale. They can be revisited,
but doing so requires amending this section.

### D-1. Active-agent model (after Zabbix)

The agent only ever initiates outbound connections. It periodically requests
a task list from the server (analogous to Zabbix active checks), runs the
tasks, and sends back the results. The server never connects to the agent.

Considered and rejected: a direct server-to-agent connection to a listening
agent endpoint (unworkable behind NAT/firewalls — exactly where a real
workstation sits); a persistent WebSocket (gives a real-time feel of "the
server asked," but needs Redis/pub-sub and reconnect handling — more than
this complex's request volume justifies).

Consequence: "a request from the server" is implemented as placing a task in
a queue that the agent picks up on its next poll. Response latency is bounded
by the poll interval (60 seconds by default), which is acceptable for a
window measured in hours.

### D-2. Transport — HTTPS + JSON, not gRPC

Exchange happens over HTTPS with a JSON body. gRPC was rejected: it
complicates traversal of corporate proxies and building the agent for
Windows, without a payoff at this traffic volume.

### D-3. Authentication — enrollment token → per-agent key

A one-time enrollment token issued by the administrator is exchanged, on
first registration, for a permanent per-agent key (after Zabbix's
autoregistration and PSK). The key is stored server-side as a hash. mTLS with
client certificates was considered and deferred: stricter, but it requires
the installer to distribute certificates and a small PKI — disproportionate
for this lab's scope. The boundary is stated in Section V.

### D-4. Inventory and heartbeat are sent on a schedule

Unlike events (principle 2), the agent sends an inventory snapshot and a
heartbeat on a schedule, not on request. Inventory is needed to detect
configuration changes between administrator requests; heartbeat marks the
agent as alive in the panel. This is the only exception to principle 2, and
it is limited to these two kinds of data.

### D-5. Data sources — native OS mechanisms

Visited websites are read from browser history databases; printing from the
CUPS log on Linux and the PrintService log on Windows; media through udev on
Linux and WMI on Windows; processes through psutil; software through the
registry on Windows and `dpkg`/`rpm` on Linux. Network traffic/DNS
interception and spooler hooks were rejected: they need high privileges, are
fragile, and reproduce poorly in CI. Each source's actual coverage is stated
honestly in Section V.

### D-6. The server stores events in PostgreSQL, the agent buffers in SQLite

Server-side: PostgreSQL, for relational integrity across agents, tasks, and
change records, `JSONB` for event payloads with varying shape, and time
indexes for window queries and daily aggregation. Agent-side: SQLite from the
standard library — a local buffer with no separate database engine on the
workstation. A TimescaleDB extension was considered and deferred as overkill
for this lab's scope.

### D-7. The agent ships both as a pip package and as a native installer

The base form is an installable Python module (wheel/sdist). Native
installers are built on top: `.msi` (WiX) for Windows 10/11 with service
installation, `.deb` and `.rpm` (nfpm) for Linux with a systemd unit.
Installers are built on a version tag in GitHub Actions. This exercises both
a plain `pip` install and end-user delivery.

### D-8. Three separate CI workflows

`ci.yml` (lint and tests on every push), `release.yml` (installers on a
tag), `security.yml` (static and composition analysis on a schedule and on
push). The split mirrors common practice: the fast per-commit loop stays
separate from the slower installer build and from the security pipeline.

### D-9. Sessions are stateless tokens with a per-operator version

An operator's session is a signed JWT that carries the `token_version` the
operator had when it was issued. The server refuses a token whose version
differs from the operator's current one, so raising that single integer ends
every session of the operator at once. A password change does so for every
session but the one it was made on, which is handed a token for the new
version; an explicit "end all sessions" does so for all of them. The raise is
one SQL statement, so two racing requests cannot both write the same value and
lose a revocation. A token with no version is refused, which is how a session
issued before this decision ends once, after the upgrade.

Considered and rejected: a denylist of token ids, or a server-side session
table (a lookup and cleanup on every request, to buy per-session revocation
that nothing needs yet); comparing the token's issue time with a "valid after"
timestamp (issue time has one-second resolution, so the token a password change
returns is ambiguous against the revocation that produced it); short-lived
tokens with a refresh token (a larger change than the problem warrants).

Consequence: only all of an operator's sessions can be ended together, never one
alone, and sessions are not listed. The boundary is stated in Section V.

### D-10. Two roles, enforced by the server on every request

An operator account is either an administrator or an observer. An observer may
read what was collected (stations, reports, inventory changes, the operating
policy) and manage their own password and sessions. Everything that acts on the
complex (asking a station for data, issuing an enrollment token, enabling or
disabling a station), the audit log, and the management of accounts are for
administrators. The server makes the check on every request, as a dependency of
the endpoint, and reads the role from the operator's row each time instead of
carrying it in the session token, so a change applies to the person's next
action with nothing to reissue. A refused observer gets 403, not 401, so the
panel can tell "you may not" from "your session ended". Hiding a control in the
panel is a courtesy and never the control itself. Two tests keep this honest: one
walks the API's own schema and fails when any operation other than sign-in,
agent enrollment, and health can be reached without a credential; the other
compares every operator endpoint with the table of what each role may do.

Accounts are only disabled, never deleted, so that the names in the audit log
keep pointing at someone. An administrator cannot change their own role or
status, so the panel's own actions cannot leave the deployment without an active
administrator.

Considered and rejected: carrying the role in the token (a demotion would wait
for the token to expire or for the session version to be raised); more than two
roles, or permissions granted one by one (nothing needs them, and a table this
short can be verified in full); limiting an observer to particular stations (a
separate feature with its own effect on the data model).

### D-11. Operating limits are stored, edited by administrators, and bounded

Three operating limits -- the longest request window, the lifetime of an
enrollment token, and the lifetime of a session -- are edited by administrators
in the panel and stored in the database as one saved set. The server's
configuration gives them their defaults, and a saved set outranks it until an
administrator returns to the defaults. One place, the policy service, decides
which value is in force, and every use (a window request, an enrollment token, a
session) reads it there afresh, so a change applies from the next use and holds
across several server processes. Sessions, tokens, and requests that already
exist keep what they were issued with.

Each value has fixed bounds. The request window's upper bound is principle 3's
four hours, and it is a constant in code, not a setting: no configuration and no
saved value can raise it, and a configured value above it is clamped to it. The
server checks that ceiling on its own, before any database read, and the agent
still checks it independently.

Considered and rejected: per-value overrides (one value could follow the
configuration while another did not, and "which is in force" would need a table
for an answer); making the ceiling a setting (principle 3 fixes it, and anyone
able to save a setting could raise it); reading the settings at each use behind
a cache that a save must invalidate (wrong across several processes); ending
existing sessions when the session length is shortened (D-9 already gives a
deliberate way to do that).

---

## IV. Spec-driven development

Work on any new capability follows this cycle:

1. **`/specify`** — `specs/NNN-name/spec.md`. Describes **what** and **why**:
   user scenarios, requirements, acceptance criteria. No technical decisions.
   Anything unclear is marked `[NEEDS CLARIFICATION: question]`.
2. **`/plan`** — `specs/NNN-name/plan.md`. Describes **how**: affected
   modules, data formats, impact on existing code. A "Constitution
   compliance" section is mandatory, checking every relevant principle
   explicitly.
3. **`/tasks`** — `specs/NNN-name/tasks.md`. Numbered steps, each a
   verifiable outcome.
4. **`/implement`** — carries out the tasks, checking them off.

Rules:

* A spec contains no module, class, or function names; those appear in the
  plan.
* A plan that violates a Section I principle is not carried out: either the
  plan changes, or the constitution is amended through the Section VII
  procedure.
* A spec's directory is numbered with a three-digit prefix; a matching git
  branch is created when working under git.
* A spec is not deleted after implementation — it remains as a record of the
  decision.

---

## V. Project boundaries

What Warden does not do and does not promise:

* **does not intercept network traffic** — visited websites are read from
  browser history (Chromium family and Firefox). Browsing in incognito mode,
  in an unsupported browser, or under a different user profile leaves no
  history entry and is invisible to the agent;
* **does not see printing outside the system spooler log** — on Linux, only
  printing through CUPS (`page_log`) is counted; on Windows, only jobs in the
  PrintService log. Printing straight to a device, bypassing the spooler, is
  not captured;
* **does not guarantee a zero-latency window for media events** — on Linux,
  udev events arrive nearly instantly; on Windows, WMI polling has a short
  interval. A brief connection between polls may go unrecorded;
* **does not collect content** — only metadata (device name, print job name
  and printer, URL and page title, process name), never file contents,
  printed documents, or page bodies;
* **does not work in a "server calls the agent" model** — the agent behind
  NAT/a firewall is reachable only via its own outbound connection (D-1); a
  response to an administrator's request arrives after up to one poll
  interval, not instantly;
* **agent authentication is a per-agent key, not mTLS** (D-3): a compromised
  key can be revoked on the server, but a client certificate would give a
  stronger binding; this is a deliberate boundary, not an oversight;
* **installers are unsigned**: Windows SmartScreen will warn on the first run
  of the `.msi`;
* **web-history collection is scoped to the account the agent service runs
  as**, not to every account on a shared machine — the default packaging
  (Section II) runs the service under a single system account for simplicity
  of reading `/var/log/cups`, `/sys/block`, and the Windows event log, none
  of which need a specific human user; browsing history sits in each human
  user's own profile directory instead. On a genuinely shared workstation,
  covering every account requires either running the service as each user in
  turn or extending the web collector to enumerate profile directories under
  every home directory — neither is done today;
* **the cross-station report shows only what stations have delivered in answer
  to window requests** (principle 2), not everything they did in the period: a
  station whose window was never requested appears empty however much happened
  on it;
* **sessions can be ended only all at once** — a password change, an explicit
  "end all sessions", or an administrator disabling the account or resetting its
  password ends every session of that operator (D-9), but one session cannot be
  listed or ended alone, and a stolen token keeps working until one of those
  happens or it expires (8 hours by default). Nothing detects a theft; ending
  sessions is the response to a suspicion. A session issued before that
  mechanism existed carries no version and is refused once after the upgrade;
* **an observer sees everything the complex has collected** — the role removes
  the ability to act and to read the audit log, not the ability to read stations'
  data, and there is no scoping to particular stations (D-10);
* **an initial or reset password is known to the administrator who set it** until
  the person changes it, and nothing forces the change;
* **two administrators acting on each other at the same instant can leave none
  active** — the rule that nobody changes their own account guarantees a
  remaining administrator only while actions are sequential; repairing that race
  needs direct access to the database;
* **a policy change applies only from the next use** -- sessions, enrollment
  tokens, and window requests that already exist keep the lifetime or limit they
  were issued with, so shortening a session or a token lifetime ends nothing that
  is already out there (D-11);
* **there is one policy for the whole deployment, and the audit log is its only
  history** -- no setting per operator or per station, no history screen, and no
  undo beyond returning to the server's configured values;
* **a saved policy outranks the server's configuration until it is reset** --
  after an administrator saves, editing the configuration alone changes nothing
  for the three values;
* **the audit log is not a complete record** — it records actions that change
  something or authenticate someone. Reads (reports, station lists, the log
  itself) are not recorded, and neither are the requests a disabled station's
  agent keeps making, so a gap in the log is not proof that nothing was read;
* **the audit log is append-only only by how the server code uses it** — the
  database has no trigger or permission that stops an account with write access
  to PostgreSQL from altering or deleting rows, so the log is not tamper-evident.

---

## VI. Quality

* Code in `server/` and `agent/` passes `ruff check`, `ruff format --check`,
  `mypy`, and `bandit` cleanly before merging — on every commit (`ci.yml`).
  Suppressions (`# noqa`, `# type: ignore`) are allowed only with a comment
  explaining why the warning is a false positive.
* Every module (`server`, `agent`) has its own unit and integration tests;
  coverage of changed code is at least 80% (principle 7).
* The web panel passes lint, unit tests (`vitest`), and a build.
* The API contract is checked against the implementation (principle 11).
* Platform collectors, beyond fixture-based tests, are verified at least once
  on a live system before being included in a release; the extent of that
  verification is stated honestly in the documentation (principle 10).
  Compiling and passing a unit test is not sufficient for them.
* CI must be green (`ubuntu-latest` and `windows-latest` for the agent)
  before a change is considered complete.

---

## VII. Amending the constitution

1. An amendment is written together with its rationale — which need the
   current rules fail to cover.
2. This file is edited; the version is bumped by semantics:
   * **MAJOR** — a principle is removed, or changed so existing code no
     longer complies;
   * **MINOR** — a principle, decision, or section is added;
   * **PATCH** — a wording clarification with no change of meaning.
3. Documents that become stale (`docs/`, `README.md`, templates) are brought
   in line by the same change.
4. The "last amended" date in the header is updated.

**Version history**

| Version | Date | Change |
|---|---|---|
| 1.0.0 | 2026-09-15 | Initial edition: principles, structure, and decisions for the Warden complex (agent-server, active-agent model, native data sources, enrollment token + TLS). The assignment's original text was folded in here as the normative source; the reference-only `Task.md` was removed from the repository |
| 1.0.1 | 2026-09-15 | PATCH: Section V gained a boundary noting that web-history collection is scoped to whichever account the agent service runs as, not every account on a shared machine — found while designing the systemd packaging (Section II, `packaging/systemd/`). No principle or decision changed |
| 1.0.2 | 2026-09-20 | PATCH: Section V gained two boundaries surfaced while planning the panel's reports and settings (`specs/002-panel-reports-and-settings/`): the cross-station report shows only events delivered through window requests (and can show duplicates, since ingestion does not deduplicate), and a password change does not end sessions already issued. No principle or decision changed |
| 1.0.3 | 2026-09-24 | PATCH: Section V gained two boundaries surfaced while planning the audit log viewer (`specs/003-audit-log-viewer/`): the log records changes and sign-ins, not reads or a disabled station's rejected requests, and it is append-only only by server code, not enforced by the database. No principle or decision changed |
| 1.1.0 | 2026-09-24 | MINOR: added decision D-9 (sessions are stateless tokens carrying a per-operator version, so a password change or an explicit request ends them) and rewrote the Section V boundary that said a password change does not end sessions, which no longer holds; what remains true is that sessions can only be ended all at once and only by their owner. See `specs/004-session-revocation/` |
| 1.2.0 | 2026-09-24 | MINOR: added decision D-10 (two roles, an administrator and an observer, enforced by the server on every request with the role read from the database and not carried in the token; accounts are disabled, never deleted) and three Section V boundaries that come with it: an observer sees everything collected, an initial or reset password is known to the administrator who set it, and two administrators acting on each other at once can leave none active. The Section V sessions boundary was widened to say an administrator can also end an operator's sessions. See `specs/005-operator-management/` |
| 1.3.0 | 2026-09-24 | MINOR: added decision D-11 (the request window limit, the enrollment token lifetime, and the session lifetime are stored as one saved set, edited by administrators within fixed bounds, and read afresh at every use; the four-hour window ceiling is a constant in code and the server's configuration is the default) and three Section V boundaries that come with it: a change applies only from the next use, one policy serves the whole deployment with the audit log as its only history, and a saved policy outranks the configuration until it is reset. See `specs/006-editable-policy/` |
| 1.3.1 | 2026-09-25 | PATCH: Section V lost the boundary noting that overlapping window requests could store the same event twice — `specs/007-event-deduplication/` closes it: ingestion now stores an event once per station, matched on category, timestamp, and payload. No principle or decision changed |
