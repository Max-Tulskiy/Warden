# Tasks: Connect a Windows agent to the server from a window and the installer

**Plan:** [./plan.md](./plan.md) · **Status:** draft · **Date:** 2026-09-25

> Each task is a verifiable outcome (a test, an endpoint, a screen), not an
> abstract action. Check it off with `[x]` once done.
>
> Tests come first and are seen to fail (red) before the implementation that
> makes them pass (green). Each `##` group below ends in one commit whose suite
> is green, and `contracts/openapi.yaml` is regenerated in the group that
> changes the API. The agent tests run against real TLS on localhost with
> `trustme` certificates, never against a system certificate store.
>
> T-47 needs a real Windows 10/11 machine and belongs to the maintainer. It is
> the one task this work cannot finish; **Status** becomes `done` only after it.

## Foundation

- [x] T-1. Work on `main`, with no branch per spec (constitution Section IV, 1.3.2); `git branch --show-current` prints `main`
- [x] T-2. In `agent/pyproject.toml` add the `gui` extra (`PySide6-Essentials`), put it in `dev`, add `pytest-qt` and `trustme` to `testing`, and add the script `warden-agent-config`; in `agent/tests/conftest.py` set `QT_QPA_PLATFORM=offscreen` by default; install into `agent/.venv`; `python -c "import PySide6.QtWidgets, pytestqt, trustme"` succeeds there

## Server — publish the authority (R-5; A-12, A-13)

- [x] T-3. Tests, failing first, in `server/tests/integration/test_tls_authority/test_tls_authority.py` with a checked-in test certificate: `GET /api/v1/tls/ca` with no credential returns 200 and a `pem` that is the certificate; `sha256` is 64 lowercase hex characters equal to the SHA-256 of the certificate's DER form; a file holding the certificate and a private key returns only the certificate; no path set, a missing file, and a file with no certificate block each return 404; the path is read at request time (a file created after startup is served)
- [x] T-4. Add `tls_ca_path` to `server/src/warden_server/config.py`, `server/src/warden_server/schemas/tls.py`, and the router `server/src/warden_server/api/tls.py` (first certificate block only, `ssl.PEM_cert_to_DER_cert`, `hashlib`), include it in `main.py`; T-3 passes
- [x] T-5. Update `server/tests/integration/test_roles/test_open_endpoints.py` (the four open operations, docstring included) and regenerate `contracts/openapi.yaml` with `python scripts/export_openapi.py`; `test_openapi_contract.py` and the open-operations test pass

## Agent — trust anchor, failures, status, waiting (R-9, R-15; A-4, A-10, A-16)

- [x] T-6. The shared test server in `agent/tests/conftest.py`: a `trustme` authority, a certificate for `localhost`, and an HTTPS server on a thread with scripted routes (`/health`, `/api/v1/tls/ca`, `/api/v1/enroll`) that records every request it receives (path, headers, body) and can swap in a new authority; a smoke test shows an unconfigured default context refuses it and a context trusting the authority accepts it
- [x] T-7. Tests, failing first, in `agent/tests/unit/test_transport/`: `build_ssl_context` refuses the test server without `ca_file` and accepts it with the authority's file; an unreadable or non-certificate `ca_file` raises `NotConfiguredError`; `classify_failure` maps an unreachable port, an untrusted certificate, a 401, a 500, and anything else to five distinct kinds; `ServerClient` without `verify` keeps working as before
- [x] T-8. Add `ca_file` to `agent/src/warden_agent/config.py` (and a test in `test_config`), `agent/src/warden_agent/errors.py` (`NotConfiguredError`), and in `core/transport.py` `build_ssl_context` (system store, `certifi`, `ca_file`), `FailureKind` with `classify_failure`, and the optional `verify` argument of `ServerClient`; T-7 passes
- [x] T-9. Tests, failing first: `AgentState` round-trips `server_url`, loads a file without it, and `is_enrolled_for(url)` ignores a trailing slash and treats a missing `server_url` as a match (`test_state`); `StatusStore` writes atomically, reads a missing or corrupt file as the default, and stores only the code values of the plan's §5 (`test_status`); `AgentScheduler` given a store records success after a poll and after an inventory pass, records the `FailureKind` of a failing one, and records nothing for a failing collection pass (`test_scheduler`)
- [x] T-10. Add `agent/src/warden_agent/status.py`, `server_url` and `is_enrolled_for` to `state.py`, and the optional store to `core/scheduler.py`; T-9 passes
- [x] T-11. Tests, failing first, in `agent/tests/unit/test_main/`: `enroll_if_needed` with no enrollment and no token raises `NotConfiguredError` (the existing `SystemExit` test is rewritten); `run` in that state records `waiting` with `not_configured`, does not return, and proceeds within one recheck once the reload callable yields a token or an enrolled state; a state whose `server_url` differs from the configured one waits with `server_changed`; an unreadable `ca_file` waits with `ca_unreadable`; a state written by the previous version and a configuration that carries a token both connect as before (A-16)
- [x] T-12. In `agent/src/warden_agent/__main__.py` make `enroll_if_needed` raise `NotConfiguredError`, and make `run` build the context, wait `CONFIG_RECHECK_SECONDS = 30` between rechecks through a `reload_settings` callable, and record `waiting` and `running`; pass the callable from `main()` and from `service/windows.py` (adjust `test_service` if it constructs `run`); T-11 passes and the existing agent suite stays green

## Configurator — text, paths, configuration file (R-8, R-10, R-17)

- [ ] T-13. Tests, failing first, in `agent/tests/unit/test_configurator/`: every string in `messages.py` contains Cyrillic; `AgentPaths.for_directory` puts the configuration, `server-ca.pem`, `state.json`, `status.json`, and `configurator.log` in one folder; the configuration file round-trips, keeps keys the administrator set (`poll_interval_seconds`, `retention_hours`, extra flat keys), writes `ca_file` and the two paths as TOML literal strings, drops `enrollment_token`, and starts from the template when the file is missing
- [ ] T-14. Add `agent/src/warden_agent/configurator/{__init__,messages,paths,config_file}.py`; T-13 passes

## Configurator — fetching and probing (R-3, R-4, R-5; A-6, A-12, A-13)

- [ ] T-15. Tests, failing first, in `agent/tests/unit/test_configurator/test_authority.py` against the T-6 server: `probe` returns *reachable and trusted*, *certificate not trusted*, *unreachable*, and *unexpected reply* for the four cases; `fetch_authority` returns a `TrustOffer` whose SHA-256 is computed locally over the DER form (a server that reports a different `sha256` is ignored) and whose subject and validity come from the certificate; a 404 gives `NoAuthority`; text that is not a certificate is refused. In `agent/tests/integration/test_full_cycle/test_authority_contract.py` the reply of the real server app (with a configured `tls_ca_path`) is parsed by the same function
- [ ] T-16. Add `agent/src/warden_agent/configurator/logic.py` with `probe`, `fetch_authority`, `TrustOffer`, and the outcome types (`FingerprintMismatch`, `NoAuthority`, `TrustNeeded`, and so on); the one request made without checking the certificate carries no token and no key; T-15 passes

## Configurator — connecting, changing server, re-trusting (R-1, R-4, R-7, R-9…R-11, R-14, R-18; A-1…A-8, A-11, A-14, A-15, A-18)

- [ ] T-17. Tests, failing first, in `agent/tests/unit/test_configurator/test_connect.py` against the T-6 server: connect with the authority and a confirmation enrolls the station and a following poll succeeds with checking on (A-1); an expected fingerprint that differs stores nothing and says so (A-2); the silent path without an expected fingerprint trusts nothing (A-3); a server already trusted asks and stores no trust (A-4); an unknown, expired, or used token stores nothing, trust included (A-5); an enrolled station given another server needs `replace`, declining changes nothing, accepting clears the old state and authority (A-7); after trusting, only files in the agent's folder differ (A-8); the token appears in no file and not in `configurator.log`, which does hold the accepted fingerprint and the outcome (A-11, A-14); every request the server received before the authority was trusted carries neither the token nor a key (A-18); a failing write of the state file leaves the station not enrolled
- [ ] T-18. Add `connect` (probe, offer, enrollment over a context that holds the candidate authority in memory, then the authority file, the configuration, and the state file last), the `configurator.log` writer, and `read_status` to `logic.py`; T-17 passes
- [ ] T-19. Tests, failing first: `retrust` after the test server's authority is replaced, confirming the new fingerprint, restores an enrolled station without enrolling again and refuses a mismatch (A-15); `read_status` reports the service state, enrollment, last contact, and last error code
- [ ] T-20. Add `retrust` to `logic.py`; T-19 passes

## Configurator — CLI and backend (R-13, R-14; A-3)

- [ ] T-21. Tests, failing first, in `agent/tests/unit/test_configurator/test_cli.py`: `--apply` exits 0 when it connects and when the station already was, and 3 when it cannot, with the reason in `configurator.log` and nothing on a console; `--ca-sha256` accepts only a match; without it an untrusted server stays untrusted; `--replace` is needed to change the server of an enrolled station; `--no-restart` does not call the backend's restart; `--check` reports the four probe results; the no-op backend reports no service
- [ ] T-22. Add `agent/src/warden_agent/configurator/backend.py` (the `Backend` protocol and a no-op backend) and `configurator/__main__.py` (`--check`, `--apply`); T-21 passes

## Configurator — controller and window (R-2, R-4, R-12, R-17; A-9, A-17)

- [ ] T-23. Tests, failing first, in `agent/tests/unit/test_configurator/test_controller.py` with synchronous stand-ins for `run_async` and `post_to_ui`: fields are disabled and the banner shown without elevation; «Подключить» is enabled only with an address; connecting an untrusted server asks for trust and shows the offer; declining stores nothing; a server change asks for confirmation; an enrolled station whose server cannot be verified offers to trust the new authority; every result maps to a Russian message
- [ ] T-24. Add `agent/src/warden_agent/configurator/controller.py`; T-23 passes
- [ ] T-25. Tests, failing first, in `agent/tests/unit/test_configurator/test_view.py` with `pytest-qt` (`pytest.importorskip("PySide6.QtWidgets")`): typing an address and a token and pressing «Подключить» reaches the controller; the trust dialog shows the fingerprint and its two buttons; the banner and disabled fields appear without elevation; the status block shows what `read_status` returns; a walk over every widget and dialog finds no visible text without Cyrillic; a screenshot of each state is written to a temporary folder
- [ ] T-26. Add `agent/src/warden_agent/configurator/view.py` (PySide6, a `QThread` running `asyncio.run`, signals back to the window, button texts from `messages.py`) and `--gui` in `configurator/__main__.py`; T-25 passes; the window is opened with `python -m warden_agent.configurator --gui --config <folder>` and looked at (screenshots kept in the scratchpad)

## Configurator — Windows backend (R-12; A-9)

- [ ] T-27. Tests, failing first, in `agent/tests/unit/test_configurator/test_windows.py` over stand-in `win32` modules, as `test_windows_service.py` does: `WindowsBackend` reports elevation both ways, maps service states, restarts the service, and builds `%ProgramData%\Warden\agent` paths; `main()` with `--apply`, `--check`, `--selftest`, and no arguments dispatches to the CLI, the CLI, the off-screen window build, and the window
- [ ] T-28. Add `agent/src/warden_agent/configurator/windows.py`; T-27 passes; no `sys.platform` or `platform.system` outside `collectors/registry.py`

## Panel — the fingerprint (R-6; A-12)

- [ ] T-29. Tests, failing first: `web/tests/unit/fingerprint.test.ts` (64 hex characters become `AB:CD:…`, case and colons ignored, anything else returned unchanged) and `web/tests/unit/agentsPage.test.tsx` (an administrator sees «Отпечаток сертификата сервера (SHA-256)» with the formatted value; a 404 shows the note that the system already verifies the certificate; a failed request shows nothing and the page still works; an observer does not see the block)
- [ ] T-30. Add `getTlsAuthority()` to `web/src/api/client.ts`, `TlsAuthority` to `types.ts`, `web/src/lib/fingerprint.ts`, and the block in `web/src/pages/AgentsPage.tsx`; T-29 passes

## Deployment and installer (R-5, R-13, R-14, R-16)

- [ ] T-31. In `docker-compose.yml` add the `ca-export` service (the `caddy` image, `caddy_data` read-only, `warden_ca` read-write, waits up to two minutes for `root.crt`, copies only that file, then idles), the `warden_ca` volume, and for `server` the read-only mount and `WARDEN_TLS_CA_PATH=/warden-ca/root.crt`; the host ports stay `443` and `80`; `docker compose config` is valid
- [ ] T-32. Update `packaging/windows/config.example.toml` (no `enrollment_token`, no placeholder `server_url`, `ca_file` described) and add `packaging/windows/THIRD-PARTY-NOTICES.txt` naming Qt and PySide6, their licence, and where the source is obtained
- [ ] T-33. Update `packaging/windows/Product.wxs` and `warden-agent.wixproj`: the `Configurator` folder installed with `Files`, the shortcut «Warden Agent — настройка», the dialog «Подключение к серверу» (three optional fields, skipped when `Installed` or `WIX_UPGRADE_DETECTED`), the properties `SERVER_URL`, `ENROLLMENT_TOKEN` (hidden) and `SERVER_CA_SHA256` as secure, the deferred `ApplyConnection` action (`--apply --replace --no-restart`, result ignored), and the exit-page option that opens the window; both files parse as XML and reference only variables the project defines
- [ ] T-34. Update `.github/workflows/release.yml` (freeze the window with `--onedir --windowed --uac-admin`, run it with `--selftest` under `QT_QPA_PLATFORM=offscreen`, hand the directory to WiX, add `workflow_dispatch` with a fallback version and uploads limited to tags) and `.github/workflows/ci.yml` (the Linux agent leg installs `libegl1 libgl1 libxkbcommon0 libdbus-1-3`); both files parse as YAML

## Constitution (Section VII)

- [ ] T-35. Amend `.specify/memory/constitution.md` to 1.5.0 (MINOR): decision D-13, D-10's sentence naming the operations open without a credential, Section II's table of agent modules, the Section V boundaries listed in the plan's §1.5, a version-history row, and the "last amended" date; the documents made stale by it are those of T-36…T-39

## Documentation (principle 9)

- [ ] T-36. Update `docs/ru/usage.md` (canonical): Windows install through the wizard and silently, the window, comparing the fingerprint, changing the server, `ca_file` for other cases; leave the honest-status paragraph for T-46
- [ ] T-37. Mirror T-36 in `docs/en/usage.md`, same section and same statements
- [ ] T-38. Update `docs/ru/architecture.md`: the trust model, the endpoint and why it is open, the status and log files, and the boundaries mirrored from Section V
- [ ] T-39. Mirror T-38 in `docs/en/architecture.md`

## Verification

- [ ] T-40. In `agent/` run `ruff check .`, `ruff format --check .`, `mypy src`, and `bandit -c pyproject.toml -r src` — all clean
- [ ] T-41. In `server/` run the same four commands with `mypy src alembic`, then `pytest --cov=warden_server --cov-report=xml --cov-fail-under=80` and `diff-cover coverage.xml --compare-branch=origin/main --fail-under=80` — green, changed-code coverage at least 80%
- [ ] T-42. In `web/` run `npm run lint`, `npm run format`, `npm test` (on Node 26 with `NODE_OPTIONS=--no-experimental-webstorage`), and `npm run build` — all clean
- [ ] T-43. In `agent/` run the full suite with `pytest --cov=warden_agent --cov-report=xml --cov-fail-under=80` and `diff-cover coverage.xml --compare-branch=origin/main --fail-under=80` — green, changed-code coverage at least 80%
- [ ] T-44. End to end on a throwaway Compose project on ports 8443/8080 (never the tracked ports; the user's `gitlab` container untouched): `GET /api/v1/tls/ca` returns the proxy's root and a fingerprint equal to `openssl x509 -fingerprint -sha256` of its `root.crt`; the server container cannot read the authority's private key; the panel's block equals what the CLI prints; `warden_agent.configurator --apply` with a matching, a wrong, and no fingerprint gives connected, refused, and untrusted; `python -m warden_agent` then polls through the verified connection and `status.json` moves; the window is opened with `--gui` and photographed in its states; the project and its volumes and images are removed
- [ ] T-45. Repository checks: no `sys.platform`/`platform.system`/platform import in the touched agent and server files except `collectors/registry.py` and `configurator/windows.py` (principle 1); a case-insensitive search of the repository (excluding `node_modules`, `.git`, `.venv`) for the project's retired transliterated name finds nothing; `docs/ru` and `docs/en` have matching headings for the pages changed; everything added under `specs/009-windows-agent-configurator/` is English apart from Russian UI text quoted verbatim to identify it; no stray files (`coverage.xml`, screenshots) in the tree
- [ ] T-46. Record the outcome and the limits of T-44 in the honest-status section of `docs/ru/usage.md` and `docs/en/usage.md`: what was checked on a real Compose stack and with the window on macOS, that the wizard, the elevation prompt, the service restart, the installer's size, and the look on Windows are not yet proven, and that the installer is compiled only by CI
- [ ] T-47. **The maintainer's manual pass on a real Windows 10/11 (A-19).** Run the `workflow_dispatch` build and note the installer's size; install with the wizard, once with values and once with none; install silently with the three properties; upgrade over an enrolled station; open the window from the Start menu through the elevation prompt; compare the fingerprint, trust, and enroll; change the server; rebuild the server's authority and re-trust; confirm the machine's certificate store is unchanged; record the results in the honest-status section of `docs/ru/usage.md` and `docs/en/usage.md`
- [ ] T-48. After T-47, set **Status** to `done` in `spec.md`, `plan.md`, and this file
