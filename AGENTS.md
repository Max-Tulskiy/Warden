# Warden — guidance for Codex

A workstation-monitoring complex for an information-security administrator,
built to counter insider activity inside a protected perimeter. Server —
FastAPI + PostgreSQL + a React panel, deployed via docker-compose. Agent — an
installable Python module running as a service on Windows 10/11 and Linux,
using an active-agent model (it initiates all contact with the server, after
Zabbix).

## The one rule that matters

**Read [.specify/memory/constitution.md](.specify/memory/constitution.md)
before doing any work.** The constitution describes the purpose, principles,
structure, and decisions already made; it takes priority over this file and
over anything agreed in chat.

## Spec-driven development

A new feature goes through the cycle: `/specify` → `/plan` → `/tasks` →
`/implement`. Specs live under `specs/NNN-name/`. Small fixes (typos,
formatting, an obvious bug) skip the spec.

`/constitution` — amend the constitution through the procedure in its
Section VII.

The complex's baseline spec is `specs/001-agent-server-complex/`.

## What must not be broken

| | Principle |
|---|---|
| 1 | Platform code lives only in a collector's platform backend module, behind a platform check; `agent.core`/`agent.buffer`/server never depend on the OS |
| 2 | The agent sends category events only for a `window_request` task; inventory and heartbeat are the exception (D-4) |
| 3 | A request window is capped at 4 hours — checked on both the server and the agent |
| 4 | The agent's local buffer keeps events no longer than the configured retention |
| 5 | Agent-server exchange is authenticated (enrollment token → per-agent key) and runs over TLS |
| 6 | Inventory is append-only snapshots + separate change records, never an overwrite |
| 7 | Server logic and the agent buffer are testable without real hardware; platform collectors are checked against fixtures in CI |
| 8 | Every action (enrollment, task, configuration change, login, error) is logged |
| 9 | Code comments and docstrings — **English**; UI text, error messages, and project documentation — **Russian**; this constitution and everything under `specs/` — **English** |
| 10 | Documentation honestly states what the complex does not collect and where coverage is partial |
| 11 | `contracts/openapi.yaml` is the source of truth for the API; a mismatch with the implementation is a defect |

## Structure

```
server/     FastAPI + PostgreSQL — ingestion, storage, panel API
agent/      warden_agent — installable Python module, Windows/Linux service
web/        React + TypeScript + Vite — administrator panel
packaging/  nfpm (.deb/.rpm), WiX (.msi)
contracts/  openapi.yaml — API contract
docs/       ru/ (canonical text), en/ (translation)
```

## Verification

**Server and agent — no real hardware needed, on every commit:**

```bash
cd server && ruff check . && ruff format --check . && mypy src alembic && bandit -c pyproject.toml -r src && pytest
cd agent && ruff check . && ruff format --check . && mypy src && bandit -c pyproject.toml -r src && pytest
```

Platform-collector unit tests run against fixtures (sample `dpkg` output, a
`page_log` line, a browser history file), not a live device — that is exactly
the practical benefit of testability without hardware (principle 7).

**Live verification of collectors on a real system is separate and manual**,
done before a release goes out (constitution Section VI); how far that
verification has actually gone on each platform is stated honestly in
`docs/ru/usage.md`.

## Build and run

```bash
docker compose up --build          # server + postgres + web + proxy
pip install -e agent[dev]           # local agent install for development
python -m warden_agent --config ./agent/config.example.toml
```
