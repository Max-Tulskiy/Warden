# Security Review: ЛР№3

## Scope

Repository-wide Standard Codex Security scan of the current Warden worktree: FastAPI server, PostgreSQL models/migrations, React panel, Python agent, Linux/Windows packaging, Docker/Caddy deployment, OpenAPI contract, tests, specs, docs, and relevant local guidance/report context.

- Scan mode: repository
- Target kind: git_worktree
- Target ID: target_sha256_ac6d969d219a5868f83ff31b770eb401fcb3c27c0b87706c261ffb5335a76df0
- Revision: eefb635ebb88b5b9d1c84724ea181fab4df55064
- Snapshot digest: codex-security-snapshot/v1:sha256:65e07c53f37a419b57f62c265b630e49071e522292aec106f525d4416137df9d
- Inventory strategy: repository
- Included paths: .
- Excluded paths: none
- Runtime or test status: No Docker stack was started and no external network access was used. Preflight passed with delegated workers available. Daybreak advisory returned not_granted.
- Scan context: User requested a Codex Security scan on this repository. Constitution priorities were applied: active-agent model, authenticated/encrypted agent-server exchange, no unsolicited category-event uploads except inventory/heartbeat, four-hour request windows on server and agent, bounded buffer retention, append-only inventory snapshots with separate change records, audit logging, honest coverage boundaries, and OpenAPI contract parity.

Limitations and exclusions:
- Dependency advisory scans were not rerun during this prompt-only scan; the repository has CI security workflow coverage for pip-audit and CodeQL.
- Docker Compose and the packaged installers were not executed.
- The local ignored .env file contained placeholder values, but because it is explicitly ignored and outside tracked product source, it is recorded as a local deployment risk rather than a canonical source finding.
- Excluded .env: Ignored local deployment state, not tracked product source. It contained placeholder values and should not be used for production; retained as local deployment risk rather than canonical source finding.
- Excluded .venv/: Virtual environments and installed dependencies were not treated as product source.
- Excluded web/node_modules/: Dependency directory is ignored and was not present in the authorized source inventory.
- Excluded dist/ and build outputs: Generated build artifacts were out of scope except where packaging definitions referenced them.

### Scan Summary

| Field | Value |
| --- | --- |
| Scan outcome | completed |
| Reportable findings | 5 |
| Severity mix | medium: 5 |
| Confidence mix | high: 4, medium: 1 |
| Coverage | complete |
| Validation mode | Static source trace with one targeted local in-memory FastAPI reproduction for report-window ingestion. |

Canonical artifacts: `scan-manifest.json`, `findings.json`, and `coverage.json`. This report is a deterministic projection of those files.

## Threat Model

Warden is an active-agent workstation monitoring system. Workstation agents collect local metadata into a SQLite buffer, initiate HTTPS/JSON calls to a FastAPI server, and a React operator panel lets authenticated administrators enroll agents, request bounded event windows, and view reports. The server deployment is Docker Compose with PostgreSQL, FastAPI, web, and Caddy TLS proxy; agent deployment is systemd on Linux and a Windows service.

### Assets

- Operator credentials and JWTs.
- Enrollment tokens and per-agent keys.
- Workstation activity metadata in the local agent buffer and central events table.
- Inventory snapshots, inventory change records, tasks, operators, and audit logs.
- Agent local state containing the agent id/key.

### Trust Boundaries

- Operator browser to FastAPI operator API via JWT bearer token.
- Agent process to FastAPI agent API via `X-Agent-Key`.
- Caddy TLS proxy to internal server and web containers.
- Server process to PostgreSQL database.
- Local OS/browser/log/registry sources to agent collectors and buffer.

### Attacker Capabilities

- Unauthenticated network caller can reach login and enrollment endpoints but needs credentials or a valid enrollment token for privileged operations.
- Holder of an operator JWT can issue enrollment tokens, place requests, and read reports.
- Holder of a valid agent key can act as that agent id for polling, report upload, and inventory upload.
- Local workstation user may read setup-time files or influence local telemetry sources depending on platform permissions.

### Security Objectives

- Only authenticated operators issue enrollment tokens, place requests, and read central reports.
- Enrollment tokens are one-time credentials that mint exactly one permanent agent key.
- Only active agents with the matching per-agent key can use agent-facing endpoints for their own id.
- Category events leave the workstation only in response to a bounded `window_request`, and the server stores only events inside that window.
- Authenticated agents cannot exhaust shared server resources with unbounded uploads.
- Operator authentication failures are abuse-resistant and audit-visible.

### Assumptions

- Production uses the Compose/Caddy or equivalent HTTPS deployment, not direct public exposure of uvicorn.
- Environment-provided production secrets are generated and protected outside tracked source; placeholder values in `.env.example` are not production secrets.
- Browser-history coverage depends on supported browser profile files existing under the runtime account home and does not include incognito/unsupported-browser activity.
- This scan inspected current local source state only, not Git history or external deployments.

## Findings

| Finding | Severity | Confidence | Detailed write-up |
| --- | --- | --- | --- |
| [Agent report ingestion accepts events outside the requested window](#finding-1) | medium | high | inline below |
| [Operator login lacks throttling and failed-attempt audit](#finding-2) | medium | high | inline below |
| [Agent upload APIs accept unbounded event and inventory payloads](#finding-3) | medium | high | inline below |
| [Packaged agent config can expose first-run enrollment tokens](#finding-4) | medium | medium | inline below |
| [Concurrent enrollment can reuse a one-time token](#finding-5) | medium | high | inline below |

### Confidence Scale

| Label | Meaning |
| --- | --- |
| high | Direct evidence supports the finding with no material unresolved blocker. |
| medium | Evidence supports a plausible issue, but material runtime or reachability proof remains. |
| low | Evidence is incomplete and the item is retained only for explicit follow-up. |

<a id="finding-1"></a>

### [1] Agent report ingestion accepts events outside the requested window

| Field | Value |
| --- | --- |
| Severity | medium |
| Confidence | high |
| Confidence rationale | Static review shows no server-side timestamp comparison, and an in-memory FastAPI reproduction accepted an event from the previous day for a one-hour task. |
| Category | improper-input-validation |
| CWE | CWE-20 |
| Affected lines | server/src/warden_server/schemas/event.py:12-22, server/src/warden_server/api/agents.py:117-125, server/src/warden_server/services/tasks.py:63-76, server/src/warden_server/api/reports.py:36-47 |

#### Summary

The report endpoint verifies task ownership but stores every submitted event timestamp without checking that it falls inside the task's requested window.

#### Root Cause

The server relies on the stock agent to select buffered events inside a requested window, but does not independently enforce the task window at the report-ingestion boundary.

**Report payload accepts arbitrary event timestamps** — `server/src/warden_server/schemas/event.py:12-22`

The authenticated agent controls each `occurred_at` value in the report body; the schema has no task-window-aware validator.

```python
class EventIn(BaseModel):
    category: EventCategory
    occurred_at: datetime
    payload: dict[str, Any] = Field(default_factory=dict)


class ReportIn(BaseModel):
    task_id: uuid.UUID
    events: list[EventIn] = Field(default_factory=list)
```

**Report endpoint checks ownership but not event range** — `server/src/warden_server/api/agents.py:117-125`

The endpoint confirms the task belongs to the agent and is not already complete, then forwards all submitted events without comparing timestamps with `task.window_start` and `task.window_end`.

```python
task = db.get(Task, payload.task_id)
if task is None or task.agent_id != agent.id:
    raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Unknown task")
if task.status == TaskStatus.COMPLETED:
    raise HTTPException(
        status.HTTP_409_CONFLICT, detail="Task has already been completed"
    )

tasks_service.complete_task(db, task=task, events=payload.events)
```

**Stored event uses the submitted timestamp** — `server/src/warden_server/services/tasks.py:63-76`

`complete_task()` persists the attacker-supplied timestamp exactly as received.

```python
stored = [
    Event(
        agent_id=task.agent_id,
        task_id=task.id,
        category=event.category,
        occurred_at=event.occurred_at,
        payload=event.payload,
    )
    for event in events
]
db.add_all(stored)
task.status = TaskStatus.COMPLETED
```

#### Validation

A one-hour task was created, then a report with an event timestamp from the previous day was submitted with the valid agent key. The endpoint returned 204 and the previous day's report returned the event.

Validation method: static source trace plus local in-memory FastAPI reproduction

**Report endpoint checks ownership but not event range** — `server/src/warden_server/api/agents.py:117-125`

The endpoint confirms the task belongs to the agent and is not already complete, then forwards all submitted events without comparing timestamps with `task.window_start` and `task.window_end`.

```python
task = db.get(Task, payload.task_id)
if task is None or task.agent_id != agent.id:
    raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Unknown task")
if task.status == TaskStatus.COMPLETED:
    raise HTTPException(
        status.HTTP_409_CONFLICT, detail="Task has already been completed"
    )

tasks_service.complete_task(db, task=task, events=payload.events)
```

**Stored event uses the submitted timestamp** — `server/src/warden_server/services/tasks.py:63-76`

`complete_task()` persists the attacker-supplied timestamp exactly as received.

```python
stored = [
    Event(
        agent_id=task.agent_id,
        task_id=task.id,
        category=event.category,
        occurred_at=event.occurred_at,
        payload=event.payload,
    )
    for event in events
]
db.add_all(stored)
task.status = TaskStatus.COMPLETED
```

Limitations:
- The reproduction used the repository's existing in-memory FastAPI test pattern rather than a live Docker/PostgreSQL deployment.

#### Dataflow

`events[].occurred_at` -\> `submit_report()` -\> `complete_task()` -\> `events.occurred_at` -\> daily report query

- **Source:** agent-controlled report body

- **Sink:** central `events` table and operator daily report

- **Outcome:** forged or excessive telemetry appears outside the approved request window

#### Reachability

Requires a valid `X-Agent-Key` for that `agent_id`; the endpoint is reachable by the enrolled agent during normal operation.

- **Attacker:** compromised or modified enrolled agent

- **Entry point:** POST `/api/v1/agents/{agent_id}/reports`

- **Outcome:** server-side report integrity violation

#### Severity

**Medium** — A compromised or modified enrolled agent can poison reports or upload more sensitive telemetry than an operator requested, but the attack is scoped to that agent identity.

Additional runtime or deployment evidence could raise or lower this severity.

#### Remediation

On report submission, require `task.kind == WINDOW_REQUEST` and `task.status == DISPATCHED`, then reject or drop every event where `event.occurred_at < task.window_start` or `event.occurred_at >= task.window_end`.

Tests:
- Assert that an event before `task.window_start` is rejected and no event row is stored.
- Assert that an event at or after `task.window_end` is rejected and no event row is stored.
- Assert that reports cannot complete pending or already completed tasks outside the expected lifecycle.

Preventive controls:
- Mirror every privacy/data-boundary invariant at the server ingestion boundary, even when the official agent already enforces it locally.

<a id="finding-2"></a>

### [2] Operator login lacks throttling and failed-attempt audit

| Field | Value |
| --- | --- |
| Severity | medium |
| Confidence | high |
| Confidence rationale | The login handler only calls `log_event` on success, and no proxy/application throttling control is present in the reviewed FastAPI or Caddy configuration. |
| Category | authentication-hardening |
| CWE | CWE-307, CWE-778 |
| Affected lines | server/src/warden_server/api/auth.py:16-34, server/src/warden_server/security.py:27-38, Caddyfile:9-15 |

#### Summary

The operator login endpoint performs Argon2 password verification and returns 401 for invalid credentials without rate limiting, lockout, or an audit record for failed attempts.

#### Root Cause

The login endpoint implements credential verification but not abuse controls or failure audit. Invalid attempts are invisible to the audit log, and repeated requests are not delayed or capped at either the proxy or application layer.

**Invalid credentials return before audit logging** — `server/src/warden_server/api/auth.py:16-34`

Failed logins raise before `log_event()`; only successful authentication is audited.

```python
invalid_credentials = HTTPException(
    status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password"
)
if operator is None or not verify_password(
    payload.password, operator.password_hash
):
    raise invalid_credentials

log_event(
    db, actor=operator.username, action="operator.login", target=operator.username
)
```

**Password verification is intentionally expensive** — `server/src/warden_server/security.py:27-38`

Repeated wrong-password attempts against an existing username drive Argon2 verification work.

```python
_password_hasher = PasswordHasher()


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _password_hasher.verify(password_hash, password)
    except VerifyMismatchError:
        return False
```

**Proxy configuration only routes API traffic** — `Caddyfile:9-15`

The checked-in proxy has no rate-limit or request-shaping rule in front of `/api/v1/auth/login`.

```caddyfile
handle /api/* {
    reverse_proxy server:8000
}

handle {
    reverse_proxy web:80
}
```

#### Validation

The reviewed routes and deployment config contain no lockout, rate limit, backoff, or failed-login audit path.

Validation method: static source trace

**Invalid credentials return before audit logging** — `server/src/warden_server/api/auth.py:16-34`

Failed logins raise before `log_event()`; only successful authentication is audited.

```python
invalid_credentials = HTTPException(
    status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password"
)
if operator is None or not verify_password(
    payload.password, operator.password_hash
):
    raise invalid_credentials

log_event(
    db, actor=operator.username, action="operator.login", target=operator.username
)
```

**Proxy configuration only routes API traffic** — `Caddyfile:9-15`

The checked-in proxy has no rate-limit or request-shaping rule in front of `/api/v1/auth/login`.

```caddyfile
handle /api/* {
    reverse_proxy server:8000
}

handle {
    reverse_proxy web:80
}
```

Limitations:
- External infrastructure rate limits, if any, were not supplied to this repository scan.

#### Dataflow

login body -\> operator lookup -\> Argon2 verification -\> 401 without audit/throttle

- **Source:** unauthenticated login request

- **Sink:** operator authentication path and server CPU

- **Outcome:** password spraying/brute-force attempts with limited visibility

#### Reachability

Login is intentionally unauthenticated and reachable through the proxy's `/api/*` route.

- **Attacker:** unauthenticated network client

- **Entry point:** POST `/api/v1/auth/login`

- **Outcome:** operator account guessing and CPU pressure

#### Severity

**Medium** — The endpoint is unauthenticated and protects the administrator panel. Generic errors and Argon2 hashing help, but missing throttling and failure audit allow password spraying and CPU pressure with poor visibility.

Additional runtime or deployment evidence could raise or lower this severity.

#### Remediation

Add per-IP and per-username rate limiting/backoff, cap username/password lengths, audit failed login attempts without exposing credential details, and alert on repeated failures. Prefer enforcing limits both at Caddy/proxy and inside the FastAPI auth path.

Tests:
- Assert failed login attempts create audit entries with action such as `operator.login_failed`.
- Assert repeated failed attempts for the same username or IP are throttled.
- Assert very large username/password bodies are rejected before expensive verification.

Preventive controls:
- Make authentication failures first-class audit events and put rate limits in front of every password-verification endpoint.

<a id="finding-3"></a>

### [3] Agent upload APIs accept unbounded event and inventory payloads

| Field | Value |
| --- | --- |
| Severity | medium |
| Confidence | high |
| Confidence rationale | Pydantic/OpenAPI schemas have no max lengths or payload-size controls, handlers build full in-memory objects, and report endpoints return unpaginated result sets. |
| Category | resource-exhaustion |
| CWE | CWE-770 |
| Affected lines | server/src/warden_server/schemas/event.py:12-22, server/src/warden_server/schemas/inventory.py:10-19, server/src/warden_server/services/tasks.py:63-74, server/src/warden_server/services/inventory.py:21-28, server/src/warden_server/api/reports.py:38-67 |

#### Summary

Authenticated agent upload schemas allow unbounded event arrays and arbitrary JSON objects, and server handlers materialize/store them without API, database, or read-side pagination limits.

#### Root Cause

The server authenticates agents but does not bound how much data one authenticated agent can send or later force the operator API to read.

**Report event list and payload objects are unconstrained** — `server/src/warden_server/schemas/event.py:12-22`

A valid agent can send any number of events with arbitrary JSON payload dictionaries.

```python
class EventIn(BaseModel):
    category: EventCategory
    occurred_at: datetime
    payload: dict[str, Any] = Field(default_factory=dict)


class ReportIn(BaseModel):
    task_id: uuid.UUID
    events: list[EventIn] = Field(default_factory=list)
```

**Inventory objects are arbitrary JSON dictionaries** — `server/src/warden_server/schemas/inventory.py:10-19`

The server accepts full arbitrary hardware/software dictionaries with no shape or size limit.

```python
class InventoryIn(BaseModel):
    """A full hardware/software snapshot sent periodically by an agent."""

    hardware: dict[str, Any]
    software: dict[str, Any]
```

**Every uploaded event is materialized before storage** — `server/src/warden_server/services/tasks.py:63-74`

Large report bodies become a large Python list of ORM objects and are written in one request.

```python
stored = [
    Event(
        agent_id=task.agent_id,
        task_id=task.id,
        category=event.category,
        occurred_at=event.occurred_at,
        payload=event.payload,
    )
    for event in events
]
db.add_all(stored)
```

#### Validation

No Pydantic `max_length`, request body limit, per-agent quota, or pagination control was found for report events, inventory objects, daily events, or inventory changes.

Validation method: static source trace

**Report event list and payload objects are unconstrained** — `server/src/warden_server/schemas/event.py:12-22`

A valid agent can send any number of events with arbitrary JSON payload dictionaries.

```python
class EventIn(BaseModel):
    category: EventCategory
    occurred_at: datetime
    payload: dict[str, Any] = Field(default_factory=dict)


class ReportIn(BaseModel):
    task_id: uuid.UUID
    events: list[EventIn] = Field(default_factory=list)
```

**Inventory objects are arbitrary JSON dictionaries** — `server/src/warden_server/schemas/inventory.py:10-19`

The server accepts full arbitrary hardware/software dictionaries with no shape or size limit.

```python
class InventoryIn(BaseModel):
    """A full hardware/software snapshot sent periodically by an agent."""

    hardware: dict[str, Any]
    software: dict[str, Any]
```

**Every uploaded event is materialized before storage** — `server/src/warden_server/services/tasks.py:63-74`

Large report bodies become a large Python list of ORM objects and are written in one request.

```python
stored = [
    Event(
        agent_id=task.agent_id,
        task_id=task.id,
        category=event.category,
        occurred_at=event.occurred_at,
        payload=event.payload,
    )
    for event in events
]
db.add_all(stored)
```

Limitations:
- No load test was run during this scan.

#### Dataflow

agent JSON body -\> Pydantic model -\> ORM/JSON serialization -\> database -\> unpaginated panel API reads

- **Source:** valid agent-controlled upload body

- **Sink:** API worker memory/CPU, PostgreSQL storage, and unpaginated report responses

- **Outcome:** resource exhaustion and degraded operator panel availability

#### Reachability

The attacker needs a valid key for one enrolled agent. The server scopes authentication by agent id, but that does not cap payload size.

- **Attacker:** compromised or malicious enrolled agent

- **Entry point:** POST `/api/v1/agents/{agent_id}/reports` or `/inventory`

- **Outcome:** server-side resource pressure and large report responses

#### Severity

**Medium** — The attack requires a valid per-agent key, but one compromised agent can consume API memory/CPU and database storage and degrade report reads for operators.

Additional runtime or deployment evidence could raise or lower this severity.

#### Remediation

Set proxy and FastAPI request body limits; add Pydantic `max_length` and JSON field constraints for report and inventory payloads; enforce per-agent upload quotas; store large batches in bounded chunks; and paginate daily event and inventory-change read endpoints.

Tests:
- Assert report uploads above the configured event count limit are rejected.
- Assert inventory payloads above configured key/byte limits are rejected.
- Assert report and inventory-change read endpoints paginate and cap response size.

Preventive controls:
- Treat every authenticated machine identity as potentially compromised and enforce server-owned resource quotas.

<a id="finding-4"></a>

### [4] Packaged agent config can expose first-run enrollment tokens

| Field | Value |
| --- | --- |
| Severity | medium |
| Confidence | medium |
| Confidence rationale | The source shows no explicit restrictive mode/ACL for the package-installed config. Actual inherited package/Windows ACL behavior was not live-tested in this scan. |
| Category | insecure-file-permissions |
| CWE | CWE-732 |
| Affected lines | agent/config.example.toml:9-13, docs/ru/usage.md:39-44, packaging/nfpm/nfpm.yaml:31-38, packaging/windows/Product.wxs:53-68, server/src/warden_server/api/agents.py:56-88 |

#### Summary

Setup instructions place a real enrollment token in the agent config before first start, but the Linux and Windows package definitions do not set owner-only permissions on that config file.

#### Root Cause

The setup flow temporarily treats `config.toml` as secret-bearing state, but package definitions treat it like ordinary configuration and do not enforce owner-only permissions or immediate token removal.

**First-run token is stored in config** — `agent/config.example.toml:9-13`

The deployment flow requires a real bearer-like enrollment token to be written to the config before first enrollment.

```toml
# One-time token issued by an administrator (POST /api/v1/enrollment-tokens
# on the server). Only needed for the very first start -- once enrolled,
# the agent's id and key live in state_path below and this line can be
# removed.
enrollment_token = "REPLACE-WITH-A-REAL-ENROLLMENT-TOKEN"
```

**Linux package sets state-directory mode, not config-file mode** — `packaging/nfpm/nfpm.yaml:31-38`

The runtime state directory is hardened, but the config file that temporarily holds the enrollment token has no explicit owner-only mode.

```yaml
- src: ../../agent/config.example.toml
  dst: /etc/warden-agent/config.toml
  type: config|noreplace

- dst: /var/lib/warden-agent
  type: dir
  file_info:
    mode: 0700
```

**Windows installer config file has no restrictive ACL** — `packaging/windows/Product.wxs:53-68`

The MSI places the setup config under `%ProgramData%` but does not declare Administrators/SYSTEM-only permissions for the file or directory.

```xml
<StandardDirectory Id="CommonAppDataFolder">
  <Directory Id="WardenAppDataFolder" Name="Warden">
    <Directory Id="AgentAppDataFolder" Name="agent">
      <Component Id="DefaultConfig" Guid="6b8e2a1f-3c4d-4e9a-8f1b-9a2d6e5c7b3a" NeverOverwrite="yes">
        <File
          Id="ConfigToml"
          Source="$(var.WardenConfigExamplePath)"
          Name="config.toml"
          KeyPath="yes" />
```

#### Validation

Linux hardens `/var/lib/warden-agent` but not `/etc/warden-agent/config.toml`; Windows WiX has no permission element for `%ProgramData%\Warden\agent\config.toml`.

Validation method: static source trace

**Linux package sets state-directory mode, not config-file mode** — `packaging/nfpm/nfpm.yaml:31-38`

The runtime state directory is hardened, but the config file that temporarily holds the enrollment token has no explicit owner-only mode.

```yaml
- src: ../../agent/config.example.toml
  dst: /etc/warden-agent/config.toml
  type: config|noreplace

- dst: /var/lib/warden-agent
  type: dir
  file_info:
    mode: 0700
```

**Windows installer config file has no restrictive ACL** — `packaging/windows/Product.wxs:53-68`

The MSI places the setup config under `%ProgramData%` but does not declare Administrators/SYSTEM-only permissions for the file or directory.

```xml
<StandardDirectory Id="CommonAppDataFolder">
  <Directory Id="WardenAppDataFolder" Name="Warden">
    <Directory Id="AgentAppDataFolder" Name="agent">
      <Component Id="DefaultConfig" Guid="6b8e2a1f-3c4d-4e9a-8f1b-9a2d6e5c7b3a" NeverOverwrite="yes">
        <File
          Id="ConfigToml"
          Source="$(var.WardenConfigExamplePath)"
          Name="config.toml"
          KeyPath="yes" />
```

Limitations:
- A live package install on Linux/Windows was not run to observe inherited permissions.

#### Dataflow

operator-issued token -\> `config.toml` -\> local read -\> `/api/v1/enroll` -\> permanent `agent_key`

- **Source:** plaintext first-run enrollment token in package-installed config

- **Sink:** permanent per-agent key returned by server

- **Outcome:** rogue enrollment or legitimate token consumption

#### Reachability

Requires local access during the setup window before the token is removed or consumed.

- **Attacker:** unprivileged local workstation user

- **Entry point:** package-installed agent config file

- **Outcome:** unauthorized agent credential issuance

#### Severity

**Medium** — A local workstation user can steal a short-lived token before enrollment and obtain a permanent agent key, but exploitation is local and setup-time bounded.

Additional runtime or deployment evidence could raise or lower this severity.

#### Remediation

Install agent config files with owner-only permissions: `0600` or root-only ownership on Linux, and Administrators/SYSTEM-only ACLs on Windows. Remove or blank `enrollment_token` automatically after successful enrollment, or pass it through a protected one-shot secret file/installer property that is deleted immediately.

Tests:
- Assert built Linux packages set `/etc/warden-agent/config.toml` to an owner-only mode.
- Add a Windows installer validation or documentation check for restrictive ACLs on `%ProgramData%\Warden\agent\config.toml`.
- Assert successful enrollment removes or clears `enrollment_token` when the agent owns the config path.

Preventive controls:
- Classify setup-time config files containing bootstrap credentials as secrets until the credential is removed.

<a id="finding-5"></a>

### [5] Concurrent enrollment can reuse a one-time token

| Field | Value |
| --- | --- |
| Severity | medium |
| Confidence | high |
| Confidence rationale | The source trace shows a non-atomic check-then-use sequence and no row lock, conditional update, or schema constraint that binds a token to exactly one agent creation. |
| Category | race-condition |
| CWE | CWE-362 |
| Affected lines | server/src/warden_server/api/agents.py:59-78, server/src/warden_server/models/enrollment.py:15-20, server/tests/integration/test_enrollment/test_enroll_flow.py:29-41 |

#### Summary

The enrollment endpoint checks `used_at` and marks the token used in separate ORM steps, so two concurrent requests with the same valid token can both pass the one-time-token check before either transaction commits.

#### Root Cause

The one-time credential invariant is implemented as a read-check-write sequence in application code instead of an atomic database claim.

**Token is read and checked before it is marked used** — `server/src/warden_server/api/agents.py:59-66`

A concurrent request can read the same row while `used_at` is still null because this is a plain select and application-level check.

```python
token_hash = hash_secret_token(payload.token)
token = db.execute(
    select(EnrollmentToken).where(EnrollmentToken.token_hash == token_hash)
).scalar_one_or_none()

now = datetime.now(UTC)
if token is None or token.used_at is not None or token.expires_at < now:
    raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Invalid or used token")
```

**Agent creation happens before token consumption is written** — `server/src/warden_server/api/agents.py:68-79`

The endpoint prepares a new permanent agent key and agent row before marking the token as used, without an atomic claim operation.

```python
agent_key = generate_secret_token()
agent = Agent(
    hostname=payload.hostname,
    os=payload.os,
    agent_key_hash=hash_secret_token(agent_key),
    status=AgentStatus.ACTIVE,
    enrolled_at=now,
    last_seen_at=now,
)
db.add(agent)
token.used_at = now
```

**Schema lacks a one-agent consumption guard** — `server/src/warden_server/models/enrollment.py:15-20`

The table records `used_at`, but no database-level relationship or conditional update enforces that only one transaction can consume the token.

```python
id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
token_hash: Mapped[str] = mapped_column(String(64), unique=True)
created_by: Mapped[str] = mapped_column(String(255))
created_at: Mapped[datetime] = mapped_column(UTCDateTime())
expires_at: Mapped[datetime] = mapped_column(UTCDateTime())
used_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
```

#### Validation

The endpoint has no `FOR UPDATE`, no conditional `UPDATE ... WHERE used_at IS NULL`, and no uniqueness constraint tying token consumption to agent creation. Existing tests cover only sequential reuse rejection.

Validation method: static source trace

**Token is read and checked before it is marked used** — `server/src/warden_server/api/agents.py:59-66`

A concurrent request can read the same row while `used_at` is still null because this is a plain select and application-level check.

```python
token_hash = hash_secret_token(payload.token)
token = db.execute(
    select(EnrollmentToken).where(EnrollmentToken.token_hash == token_hash)
).scalar_one_or_none()

now = datetime.now(UTC)
if token is None or token.used_at is not None or token.expires_at < now:
    raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Invalid or used token")
```

**Agent creation happens before token consumption is written** — `server/src/warden_server/api/agents.py:68-79`

The endpoint prepares a new permanent agent key and agent row before marking the token as used, without an atomic claim operation.

```python
agent_key = generate_secret_token()
agent = Agent(
    hostname=payload.hostname,
    os=payload.os,
    agent_key_hash=hash_secret_token(agent_key),
    status=AgentStatus.ACTIVE,
    enrolled_at=now,
    last_seen_at=now,
)
db.add(agent)
token.used_at = now
```

**Schema lacks a one-agent consumption guard** — `server/src/warden_server/models/enrollment.py:15-20`

The table records `used_at`, but no database-level relationship or conditional update enforces that only one transaction can consume the token.

```python
id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
token_hash: Mapped[str] = mapped_column(String(64), unique=True)
created_by: Mapped[str] = mapped_column(String(255))
created_at: Mapped[datetime] = mapped_column(UTCDateTime())
expires_at: Mapped[datetime] = mapped_column(UTCDateTime())
used_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
```

Limitations:
- No live concurrent PostgreSQL reproduction was run in this scan.

#### Dataflow

enrollment token -\> token row lookup -\> application `used_at` check -\> `Agent(...)` creation -\> permanent agent key

- **Source:** valid enrollment token held by an attacker

- **Sink:** new `agents` row and returned `agent_key`

- **Outcome:** unauthorized enrolled agent identity

#### Reachability

The `/api/v1/enroll` endpoint is intentionally unauthenticated except for possession of the enrollment token.

- **Attacker:** holder of a valid enrollment token

- **Entry point:** POST `/api/v1/enroll`

- **Outcome:** multiple permanent agent credentials or denial of legitimate enrollment

#### Severity

**Medium** — A valid enrollment token is required, but a successful race can mint unauthorized permanent agent keys and undermine station attribution.

Additional runtime or deployment evidence could raise or lower this severity.

#### Remediation

Claim enrollment tokens atomically, for example with `UPDATE enrollment_tokens SET used_at = :now WHERE token_hash = :hash AND used_at IS NULL AND expires_at >= :now RETURNING id`, then create the agent only if exactly one row was claimed. Alternatively, select the row `FOR UPDATE` in PostgreSQL and re-check before creating the agent.

Tests:
- Add a PostgreSQL integration test that sends concurrent enrollment requests with the same token and asserts exactly one succeeds.
- Assert that sequential reuse still returns 400 after the atomic claim change.

Preventive controls:
- Keep one-time credential state transitions in database-atomic operations rather than application read-check-write sequences.

## Reviewed Surfaces

| Surface | Risk Area | Outcome | Notes |
| --- | --- | --- | --- |
| Operator authentication and session authorization | not recorded | Reported | Reported missing throttling and failed-login audit. Password hashing uses Argon2id and invalid-credential messages are generic. |
| Agent enrollment token lifecycle | not recorded | Reported | Reported non-atomic one-time token consumption. Sequential token reuse is rejected; concurrency remains unguarded. |
| Per-agent API authentication | not recorded | No issue found | `require_agent` binds the supplied key to the path `agent_id` and active status; no cross-agent key reuse issue was found. |
| Window request placement, polling, and report ingestion | not recorded | Reported | Reported missing server-side validation that event timestamps fit the task window. Operator request placement and stock-agent response enforce the four-hour cap. |
| Agent report and inventory upload resource limits | not recorded | Reported | Reported unbounded report arrays, arbitrary JSON inventory payloads, and unpaginated operator reads. |
| Inventory snapshot and change detection | not recorded | No issue found | Snapshots are append-only and changes are recorded separately; no SQL injection or overwrite issue found. |
| Agent local state, buffer, and package permissions | not recorded | Reported | The older Linux state/buffer permission issue appears fixed in current source. Reported remaining setup-time config-token permission gap. |
| Platform collectors and local parsers | not recorded | No issue found | No command injection path found; browser history SQLite queries use fixed SQL with parameters; Windows PrintService XML parsing is local OS event data, not a remote XML interface. |
| React panel rendering and API client | not recorded | No issue found | Agent-controlled strings are rendered as React text nodes. No raw HTML or eval-like sink was found. JWT in localStorage remains XSS-sensitive, but no exploitable XSS source/sink pair was identified. |
| Docker, Caddy, CI, release, and dependency workflow | not recorded | No issue found | Compose requires database/JWT secret variables and routes traffic through Caddy TLS. Dependency advisories were not rerun in this scan; CI includes CodeQL and pip-audit. |
| Ignored local .env placeholder values | not recorded | Rejected | A baseline worker flagged the local ignored `.env` as critical. It was not included as a canonical source finding because `.env` is explicitly ignored (`.gitignore:31`) and not tracked product source. The deployment risk remains real if the local placeholder file is used unchanged. |

## Open Questions And Follow Up

- Actual inherited filesystem permissions for package-installed `/etc/warden-agent/config.toml` and `%ProgramData%\Warden\agent\config.toml` should be verified on built packages.
- Any external infrastructure rate limits in front of Caddy/FastAPI were not supplied to this source scan.
