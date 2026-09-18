# Security Review: Warden lab repository

## Scope

Prompt-only Codex Security repository scan of server, agent, web panel, packaging, deployment, documentation, specs, and the untracked AGENTS.md guidance file present in the worktree.

- Scan mode: repository
- Target kind: git_worktree
- Target ID: e715cf06df39f7427a00f73f7919c84778f8e474dba09b520c621d877657235c
- Revision: eefb635ebb88b5b9d1c84724ea181fab4df55064
- Snapshot digest: codex-security-snapshot/v1:sha256:ee41cbef4dd857346b5fd91f8283467cfe26b72db8621394049cbd6e17a44c79
- Inventory strategy: repository
- Included paths: .
- Excluded paths: none
- Runtime or test status: No full runtime stack was started. Validation used static source review plus a local file-mode reproduction through agent/.venv.
- Artifacts reviewed: server/src/warden_server/api/\*.py, server/src/warden_server/security.py, server/src/warden_server/config.py, agent/src/warden_agent/\*\*/\*.py, web/src/\*\*/\*.ts\*, docker-compose.yml, Caddyfile, packaging/\*\*, docs/\*\*, specs/\*\*, AGENTS.md
- Scan context: No host-backed Codex Security aggregation tools were exposed in this session; the scan was completed headlessly and sealed with the local finalizer.

Limitations and exclusions:
- Docker Compose was not started during this scan.
- Dependency advisory checks were not rerun; the repository has a scheduled pip-audit workflow for server and agent dependencies.

### Scan Summary

| Field | Value |
| --- | --- |
| Scan outcome | completed |
| Reportable findings | 1 |
| Severity mix | medium: 1 |
| Confidence mix | high: 1 |
| Coverage | complete |
| Validation mode | static source trace with targeted local reproduction |

Canonical artifacts: `scan-manifest.json`, `findings.json`, and `coverage.json`. This report is a deterministic projection of those files.

## Threat Model

Warden separates operator, agent, and local workstation trust boundaries. Operator APIs use JWT bearer tokens, agents use per-agent keys in X-Agent-Key, and Linux/Windows agents collect sensitive endpoint telemetry into local storage before sending bounded reports to the server.

### Assets

- operator JWT signing secret and operator sessions
- per-agent enrollment keys and X-Agent-Key credentials
- local endpoint telemetry buffer: web history, process, printing, removable media, and inventory metadata
- server-side PostgreSQL records and audit log

### Trust Boundaries

- browser panel to FastAPI operator API
- agent process to FastAPI agent API over HTTPS
- local unprivileged workstation users to root/LocalSystem agent state
- reverse proxy TLS boundary in front of server and web containers

### Attacker Capabilities

- local unprivileged user on a monitored workstation
- network client that can reach public API endpoints
- malicious or compromised enrolled agent limited to its own agent_id

### Security Objectives

- Only operators can issue enrollment tokens and read panel reports.
- Only the enrolled agent possessing its own key can poll tasks or submit reports for that agent_id.
- Sensitive local telemetry and persistent agent credentials are not readable by ordinary workstation users.
- Server-side request windows remain bounded and auditable.

### Assumptions

- Linux package defaults run the agent as root through systemd as documented by the service unit.
- The default deployment path for Linux agents is /var/lib/warden-agent according to config.example.toml and systemd packaging.

## Findings

| Finding | Severity | Confidence | Detailed write-up |
| --- | --- | --- | --- |
| [Local users can read the Linux agent key and monitoring buffer](#finding-1) | medium | high | inline below |

### Confidence Scale

| Label | Meaning |
| --- | --- |
| high | Direct evidence supports the finding with no material unresolved blocker. |
| medium | Evidence supports a plausible issue, but material runtime or reachability proof remains. |
| low | Evidence is incomplete and the item is retained only for explicit follow-up. |

<a id="finding-1"></a>

### [1] Local users can read the Linux agent key and monitoring buffer

| Field | Value |
| --- | --- |
| Severity | medium |
| Confidence | high |
| Confidence rationale | Static source review shows no restrictive mode is applied to the Linux state directory, state file, or SQLite buffer; a local reproduction under umask 022 created both files as 0644. |
| Category | insecure-file-permissions |
| CWE | CWE-276, CWE-732 |
| Affected lines | agent/src/warden_agent/state.py:27-28, agent/src/warden_agent/buffer/store.py:47-52, packaging/systemd/warden-agent.service:14-20, packaging/nfpm/nfpm.yaml:31-36 |

#### Summary

A local workstation user can read the Linux agent state file and SQLite buffer when the service runs with the packaged defaults. The state file contains the permanent per-agent key used as `X-Agent-Key`, and the buffer contains collected endpoint telemetry.

#### Root Cause

The violated invariant is that local agent credentials and telemetry must be readable only by the service account/root. Packaging places both runtime files under `/var/lib/warden-agent` without an owner-only directory mode, and the Python code creates `state.json` and `buffer.db` through APIs that inherit the process umask instead of explicitly applying `0600` file permissions.

**Linux package deploys config and state directory without a restrictive mode** — `packaging/nfpm/nfpm.yaml:31-36`

The Linux package creates `/var/lib/warden-agent` but does not set owner-only directory permissions, so the runtime files created there inherit default packaging/system umask behavior.

```yaml
  - src: ../../agent/config.example.toml
    dst: /etc/warden-agent/config.toml
    type: config|noreplace

  - dst: /var/lib/warden-agent
    type: dir
```

**systemd unit uses the shared state directory as the working directory** — `packaging/systemd/warden-agent.service:14-20`

The service stores agent runtime state under `/var/lib/warden-agent` and does not set `StateDirectoryMode=0700` or another equivalent owner-only control.

```ini
[Service]
Type=simple
ExecStart=/usr/bin/warden-agent --config /etc/warden-agent/config.toml
Restart=on-failure
RestartSec=5
StateDirectory=warden-agent
WorkingDirectory=/var/lib/warden-agent
```

**Default Linux config places both sensitive files in the state directory** — `agent/config.example.toml:24-25`

`state_path` holds the permanent per-agent credential and `buffer_path` holds collected endpoint events; both are placed in the directory whose permissions are not hardened by packaging.

```toml
buffer_path = "/var/lib/warden-agent/buffer.db"
state_path = "/var/lib/warden-agent/state.json"
```

**Agent state is written without chmod or atomic owner-only creation** — `agent/src/warden_agent/state.py:27-28`

`Path.write_text()` creates the state file using the process umask. With a normal `022` umask, the file is mode `0644`, exposing `agent_key` to local users who can traverse the state directory.

```python
    def save(self, path: Path) -> None:
        path.write_text(json.dumps(self.model_dump()), encoding="utf-8")
```

**SQLite buffer is created without restrictive mode** — `agent/src/warden_agent/buffer/store.py:47-52`

`sqlite3.connect()` creates `buffer.db` using the process umask. The buffer stores web, process, printing, removable media, and inventory events before report upload.

```python
    def __init__(self, path: Path) -> None:
        self._lock = threading.Lock()
        self._connection = sqlite3.connect(str(path), check_same_thread=False)
        with self._lock:
            self._connection.executescript(_SCHEMA)
            self._connection.commit()
```

**The stolen key is the credential accepted by agent endpoints** — `server/src/warden_server/api/deps.py:18-41`

Once a local user reads `agent_key` from `state.json`, that value is sufficient to authenticate as the same active agent for task polling, report submission, and inventory upload endpoints.

```python
def require_agent(
    agent_id: uuid.UUID = Path(...),
    x_agent_key: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> Agent:
    unauthorized = HTTPException(
        status.HTTP_401_UNAUTHORIZED, detail="Invalid agent credentials"
    )
    if not x_agent_key:
        raise unauthorized
    agent = db.get(Agent, agent_id)
    if (
        agent is None
        or agent.status != AgentStatus.ACTIVE
        or not verify_secret_token(x_agent_key, agent.agent_key_hash)
    ):
        raise unauthorized
    return agent
```

#### Validation

The source trace follows packaged Linux paths to the state and buffer creation points. Running the real `AgentState.save()` and `Buffer()` creation code through `agent/.venv` with umask `022` produced `state.json` and `buffer.db` as `0644`, confirming local readability under default conditions.

Validation method: static source trace plus local mode reproduction

**Linux package deploys config and state directory without a restrictive mode** — `packaging/nfpm/nfpm.yaml:31-36`

The Linux package creates `/var/lib/warden-agent` but does not set owner-only directory permissions, so the runtime files created there inherit default packaging/system umask behavior.

```yaml
  - src: ../../agent/config.example.toml
    dst: /etc/warden-agent/config.toml
    type: config|noreplace

  - dst: /var/lib/warden-agent
    type: dir
```

**systemd unit uses the shared state directory as the working directory** — `packaging/systemd/warden-agent.service:14-20`

The service stores agent runtime state under `/var/lib/warden-agent` and does not set `StateDirectoryMode=0700` or another equivalent owner-only control.

```ini
[Service]
Type=simple
ExecStart=/usr/bin/warden-agent --config /etc/warden-agent/config.toml
Restart=on-failure
RestartSec=5
StateDirectory=warden-agent
WorkingDirectory=/var/lib/warden-agent
```

**Default Linux config places both sensitive files in the state directory** — `agent/config.example.toml:24-25`

`state_path` holds the permanent per-agent credential and `buffer_path` holds collected endpoint events; both are placed in the directory whose permissions are not hardened by packaging.

```toml
buffer_path = "/var/lib/warden-agent/buffer.db"
state_path = "/var/lib/warden-agent/state.json"
```

**Agent state is written without chmod or atomic owner-only creation** — `agent/src/warden_agent/state.py:27-28`

`Path.write_text()` creates the state file using the process umask. With a normal `022` umask, the file is mode `0644`, exposing `agent_key` to local users who can traverse the state directory.

```python
    def save(self, path: Path) -> None:
        path.write_text(json.dumps(self.model_dump()), encoding="utf-8")
```

**SQLite buffer is created without restrictive mode** — `agent/src/warden_agent/buffer/store.py:47-52`

`sqlite3.connect()` creates `buffer.db` using the process umask. The buffer stores web, process, printing, removable media, and inventory events before report upload.

```python
    def __init__(self, path: Path) -> None:
        self._lock = threading.Lock()
        self._connection = sqlite3.connect(str(path), check_same_thread=False)
        with self._lock:
            self._connection.executescript(_SCHEMA)
            self._connection.commit()
```

Assertions:
- `state.json` contains `agent_id` and `agent_key` after enrollment.
- `buffer.db` stores collected local event payloads until retention pruning.
- The server accepts the plaintext `agent_key` through `X-Agent-Key` for that same `agent_id`.

Limitations:
- A full Linux package install under systemd was not executed during this scan.
- The server correctly scopes the stolen key to its own agent_id, so this is endpoint impersonation rather than cross-agent authorization bypass.

#### Dataflow

Linux package paths -\> systemd state directory -\> `AgentState.save()` / `Buffer()` -\> world-readable files -\> `require_agent()` authentication

- **Source:** local filesystem access by an unprivileged workstation user

- **Sink:** persistent agent credential and local SQLite telemetry buffer

- **Outcome:** read sensitive endpoint telemetry and impersonate the enrolled agent for its own server endpoints

**Linux package deploys config and state directory without a restrictive mode** — `packaging/nfpm/nfpm.yaml:31-36`

The Linux package creates `/var/lib/warden-agent` but does not set owner-only directory permissions, so the runtime files created there inherit default packaging/system umask behavior.

```yaml
  - src: ../../agent/config.example.toml
    dst: /etc/warden-agent/config.toml
    type: config|noreplace

  - dst: /var/lib/warden-agent
    type: dir
```

**Agent state is written without chmod or atomic owner-only creation** — `agent/src/warden_agent/state.py:27-28`

`Path.write_text()` creates the state file using the process umask. With a normal `022` umask, the file is mode `0644`, exposing `agent_key` to local users who can traverse the state directory.

```python
    def save(self, path: Path) -> None:
        path.write_text(json.dumps(self.model_dump()), encoding="utf-8")
```

**SQLite buffer is created without restrictive mode** — `agent/src/warden_agent/buffer/store.py:47-52`

`sqlite3.connect()` creates `buffer.db` using the process umask. The buffer stores web, process, printing, removable media, and inventory events before report upload.

```python
    def __init__(self, path: Path) -> None:
        self._lock = threading.Lock()
        self._connection = sqlite3.connect(str(path), check_same_thread=False)
        with self._lock:
            self._connection.executescript(_SCHEMA)
            self._connection.commit()
```

**The stolen key is the credential accepted by agent endpoints** — `server/src/warden_server/api/deps.py:18-41`

Once a local user reads `agent_key` from `state.json`, that value is sufficient to authenticate as the same active agent for task polling, report submission, and inventory upload endpoints.

```python
def require_agent(
    agent_id: uuid.UUID = Path(...),
    x_agent_key: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> Agent:
    unauthorized = HTTPException(
        status.HTTP_401_UNAUTHORIZED, detail="Invalid agent credentials"
    )
    if not x_agent_key:
        raise unauthorized
    agent = db.get(Agent, agent_id)
    if (
        agent is None
        or agent.status != AgentStatus.ACTIVE
        or not verify_secret_token(x_agent_key, agent.agent_key_hash)
    ):
        raise unauthorized
    return agent
```

**Default Linux config places both sensitive files in the state directory** — `agent/config.example.toml:24-25`

`state_path` holds the permanent per-agent credential and `buffer_path` holds collected endpoint events; both are placed in the directory whose permissions are not hardened by packaging.

```toml
buffer_path = "/var/lib/warden-agent/buffer.db"
state_path = "/var/lib/warden-agent/state.json"
```

#### Reachability

The attacker needs shell or filesystem access as any local user on the monitored Linux host while default package/service settings are in use.

- **Attacker:** local unprivileged workstation user

- **Entry point:** /var/lib/warden-agent/state.json and /var/lib/warden-agent/buffer.db

- **Outcome:** agent credential disclosure, telemetry disclosure, and falsified agent reports for that workstation

Limitations:
- The attack is local to the monitored workstation.

#### Severity

**Medium** — The attack requires local low-privilege access to the workstation, but it discloses sensitive telemetry and enables impersonation of that station to poll tasks and submit falsified reports.

Severity would increase if the agent key could authorize cross-agent access; the server currently scopes the key to the URL agent_id. Severity would decrease if deployment scripts always created a 0700 state directory and 0600 files before first start.

Impact assessment:
- **Level:** medium
- **Why:** The issue compromises one endpoint agent identity and sensitive local monitoring data, but it does not grant operator panel access or affect other agents because server-side authentication checks the URL `agent_id`.

Likelihood assessment:
- **Level:** medium
- **Why:** Default Linux filesystem behavior commonly uses umask `022`; no code or packaging control forces owner-only modes before the files are created.

#### Remediation

Create the Linux state directory with owner-only permissions and create/chmod `state.json` and `buffer.db` as `0600` before storing credentials or telemetry.

Tests:
- Assert that `AgentState.save()` creates a new state file with mode `0600` even when the process umask is `022`.
- Assert that `Buffer(path)` creates a new SQLite database with mode `0600` even when the process umask is `022`.
- Add packaging validation that the Linux package or systemd unit sets `/var/lib/warden-agent` to an owner-only mode such as `0700`.

Preventive controls:
- Centralize sensitive-file creation in one helper that uses `os.open(..., 0o600)` or immediately applies `chmod(0o600)` before writing secrets.
- Set `StateDirectoryMode=0700` in the systemd unit and explicit `file_info.mode`/ownership for package-created config and state paths.
- Document that local agent state contains a bearer credential and must be protected like a secret.

## Reviewed Surfaces

| Surface | Risk Area | Outcome | Notes |
| --- | --- | --- | --- |
| Operator authentication and JWT authorization | authentication | No issue found | Login, password hashing, JWT decode, and operator dependencies were reviewed. The source default JWT secret is weak for direct-from-source production runs, but the docker-compose deployment requires WARDEN_JWT_SECRET and documentation instructs replacement; retained as hardening guidance rather than a reportable exploit in the packaged deployment surface. |
| Agent enrollment and per-agent authentication | authentication/authorization | No issue found | Enrollment tokens and agent keys are high entropy, server-side storage uses hashes, and `require_agent` binds the supplied key to the path `agent_id`. |
| Linux agent local state and event buffer permissions | local credential and telemetry disclosure | Reported | Reported because packaged Linux defaults can create `state.json` and `buffer.db` as local-readable files. |
| Window request creation, polling, and report upload | authorization/business logic | No issue found | Server caps request windows, verifies agent ownership for reports, and uses typed schemas for event categories. |
| Inventory ingestion and event storage | data integrity and injection | No issue found | SQLAlchemy parameterized queries are used; event payloads are stored as JSON and rendered by React without direct HTML injection patterns. |
| Agent collectors and OS integrations | command execution/local parsing | No issue found | Reviewed subprocess, SQLite history readers, removable-media, printing, process, and inventory collectors. Commands are fixed argument lists with `shell=False`; browser history reads use read-only parameterized SQLite queries. |
| React web panel API client and session state | XSS/session storage/CSRF | No issue found | No `dangerouslySetInnerHTML` or raw HTML sinks were found. JWT is stored in localStorage, which is a known XSS-sensitive choice, but no exploitable XSS source/sink pair was identified in this scan. |
| Docker, Caddy, nginx, and package deployment | deployment security | No issue found | Docker compose requires database and JWT secrets, Caddy terminates TLS, and the server container drops to a non-root user. The Linux agent packaging issue is tracked separately in the reported local-storage surface. |
| CI security workflow, documentation, specifications, and AGENTS guidance | supply-chain/documentation drift | No issue found | Reviewed security workflow, usage/architecture docs, spec files, and the untracked AGENTS.md guidance file; no separate reportable issue was identified. |
