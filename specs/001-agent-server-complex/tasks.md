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

Five findings from `security-reports/codex-security/2026-09-18_092429Z_standard_scan` (all medium):

- [x] T-43. Claim enrollment tokens with a single conditional `UPDATE` instead of a SELECT-then-check, closing a concurrent-reuse race (CWE-362, finding "Concurrent enrollment can reuse a one-time token"); a rejected claim is now audited as `agent.enroll_rejected`
- [x] T-44. Reject a report with 400 if any event falls outside its task's `[window_start, window_end)`, and require the task to be `DISPATCHED` rather than merely "not completed" (CWE-20, finding "Agent report ingestion accepts events outside the requested window"); audited as `agent.report_out_of_window`
- [x] T-45. Cap `ReportIn.events` at 10,000 and `InventoryIn.hardware`/`software` at 10,000 entries each; add `limit`/`offset` pagination (default 500, max 2000) to the daily-report and inventory-change-timeline read endpoints, with a "Показать ещё" control in the panel; add a `request_body max_size 16MB` cap in `Caddyfile` (CWE-770, finding "Agent upload APIs accept unbounded event and inventory payloads")
- [x] T-46. Audit failed operator logins as `operator.login_failed` (reason only, never the password) and throttle repeated failures per username via a new in-process `services/throttle.py` (5 attempts / 5 minutes, audited as `operator.login_throttled`); cap `LoginRequest` username/password length (CWE-307/CWE-778, finding "Operator login lacks throttling and failed-attempt audit")
- [x] T-47. Restrict the packaged agent config to owner-only: `/etc/warden-agent` to `0700` and `config.toml` to `0600` in `packaging/nfpm/nfpm.yaml` (verified by building real `.deb`/`.rpm` packages locally); `util:PermissionEx` (SYSTEM/Administrators only) on the Windows config component in `packaging/windows/Product.wxs` (unverified -- no Windows machine, see plan.md §8) (CWE-732, finding "Packaged agent config can expose first-run enrollment tokens")

All five verified end to end against the real docker-compose stack (Caddy + PostgreSQL), not just the SQLite test suite.
