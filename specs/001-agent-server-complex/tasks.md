# Tasks: Agent-server complex

**Plan:** [./plan.md](./plan.md) · **Status:** done · **Date:** 2026-09-15

## Foundation

- [x] T-1. Constitution, spec-kit templates, `.claude/commands/`
- [x] T-2. Spec and plan for this feature
- [x] T-3. Repository skeleton: `server/`, `agent/`, `web/` with `pyproject.toml`/`package.json`, tooling (ruff, mypy, bandit)
- [x] T-4. `contracts/openapi.yaml` — contract for enroll/tasks/reports/inventory/requests/auth

## Server

- [x] T-5. SQLAlchemy models and the initial Alembic migration
- [x] T-6. `POST /api/v1/enroll` — enrollment with a one-time token
- [x] T-7. `GET /api/v1/agents/{id}/tasks`, `POST /api/v1/agents/{id}/reports`
- [x] T-8. `POST /api/v1/agents/{id}/inventory` + configuration-change detector
- [x] T-9. `POST /api/v1/agents/{id}/requests` with ≤4h window validation (operator)
- [x] T-10. Operator auth (`POST /api/v1/auth/login`, JWT) and agent auth (hashed key)
- [x] T-11. Read endpoints for the panel: station list, daily report, change timeline
- [x] T-12. Audit log (`audit_log`) on every endpoint

## Agent

- [x] T-13. `warden_agent.buffer.Buffer` — SQLite, window queries, retention pruning
- [x] T-14. `warden_agent.core.transport` — enroll/poll/push/heartbeat, backoff
- [x] T-15. `warden_agent.core.scheduler` — three loops (collection, task polling, inventory)
- [x] T-16. Inventory collector (Linux: `dpkg`/`rpm`+`psutil`; Windows: registry+`psutil`)
- [x] T-17. Removable-media collector (Linux: `/sys/block`+`/proc/mounts` polling, no `pyudev` dependency needed; Windows: `pywin32`)
- [x] T-18. Printing collector (Linux: CUPS `page_log`; Windows: PrintService Event 307)
- [x] T-19. Process collector (`psutil`, cross-platform)
- [x] T-20. Web-history collector (Chromium profiles, Firefox `places.sqlite`)
- [x] T-21. Service entry points: systemd (Linux), Windows service (`pywin32`)

## Web panel

- [x] T-22. Station list with status and last-seen
- [x] T-23. Window-request form (≤4h, client-side check)
- [x] T-24. Station event view by category for the day's report
- [x] T-25. Configuration-change timeline
- [x] T-26. Operator login

## Tests

- [x] T-27. Server unit tests: window validation, change detector, authentication
- [x] T-28. Server integration tests: enroll → task → report cycle against a test database
- [x] T-29. Agent unit tests: buffer/retention, backoff, collector fixture parsing
- [x] T-30. Agent integration tests: a full exchange against a test server (real server app over ASGI transport)
- [x] T-31. Contract tests: `schemathesis` against `contracts/openapi.yaml` (a byte-for-byte equality test guards drift locally; schemathesis fuzzing runs as its own CI job, T-36)

## Documentation

- [x] T-32. `docs/ru/architecture.md` + `docs/en/architecture.md`
- [x] T-33. `docs/ru/usage.md` + `docs/en/usage.md` (including an honest status of live Windows-collector verification)
- [x] T-34. `README.md` with the assignment-function coverage table

## Infrastructure

- [x] T-35. `docker-compose.yml` (server + postgres + web + TLS-terminating reverse proxy) -- verified end to end: build, migrate, seed admin, login, enroll, all through the real stack
- [x] T-36. `.github/workflows/ci.yml` — ruff/mypy/bandit + server/agent tests (ubuntu+windows matrix) + web + contract
- [x] T-37. `.github/workflows/security.yml` — CodeQL, `pip-audit`
- [x] T-38. `packaging/nfpm/` (.deb/.rpm, verified building real packages locally) + `packaging/windows/` (WiX .msi, unverified -- no Windows machine, see plan.md §8) + `.github/workflows/release.yml`

## Final checks

- [x] T-39. Run `ruff`, `mypy`, `bandit` on `server/` and `agent/` -- all clean
- [x] T-40. Run the full test suite of every module -- server 32/32 (97% cov), agent 89/89 + 5 platform-gated skips (81% cov), web 6/6, build clean
- [x] T-41. Add a panel-side enrollment-token flow for registering new agents

## Security hardening

- [x] T-42. Fix insecure Linux agent file permissions found by `security-reports/codex-security/scan_warden_20260916_001` (finding 1, medium): `AgentState.save()` and `Buffer.__init__` now `chmod(0o600)` the state file and SQLite buffer regardless of process umask; `packaging/systemd/warden-agent.service` sets `StateDirectoryMode=0700` and `packaging/nfpm/nfpm.yaml` sets `file_info.mode: 0700` on `/var/lib/warden-agent`; added umask-022 regression tests for both file creators
