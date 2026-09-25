# Implementation plan: Connect a Windows agent to the server from a window and the installer, trusting the server's own certificate authority

**Spec:** [./spec.md](./spec.md) · **Status:** draft · **Date:** 2026-09-25

---

## 1. Approach

Five pieces, in the order they are built: the agent's trust and status
plumbing, the server's publication of its certificate authority, the
configurator (logic, then window), the deployment and installer, and the
constitution and documents.

### 1.1 Agent: trust, waiting, status (`agent.core` and next to it)

* **A trust anchor in the configuration.** `AgentSettings` gains
  `ca_file: Path | None`. `core/transport.py` gains `build_ssl_context(ca_file)`:
  `ssl.create_default_context()` (which loads the operating system's store by
  itself, so no OS branching is written here), plus the `certifi` bundle that
  httpx used until now, plus `ca_file` when set. The `certifi` bundle stays
  because httpx's own default is `certifi` and *not* the system store, so
  switching to the system store alone would silently drop trust the agent has
  today. `ServerClient` takes an optional `verify` context and hands it to
  `httpx.AsyncClient`; a caller that passes nothing keeps the old behavior.
  The same module gains `classify_failure(exc) -> FailureKind` (*unreachable*,
  *certificate not trusted*, *credential refused*, *server error*, *other*), which
  walks the exception's cause chain once; the scheduler's status and the
  configurator's `probe` both use it, so the two never disagree about what went
  wrong. `NotConfiguredError` lives in a small `errors.py`.
* **Waiting instead of exiting.** `enroll_if_needed` raises a new
  `NotConfiguredError` instead of `SystemExit`. `run()` catches it (and a
  `ca_file` that cannot be read), records a `waiting` status, sleeps
  `CONFIG_RECHECK_SECONDS = 30`, and reloads settings and state through a
  `reload_settings` callable that both entry points pass in (`main()` and the
  Windows service). The station therefore starts working within 30 seconds of
  being configured, well inside R-15's one minute, with no restart.
* **Which server a key belongs to.** `AgentState` gains `server_url`, written at
  enrollment. A state whose server differs from the configured one counts as
  not enrolled and the agent waits and says why. This makes R-11 hold when
  the configuration is changed by hand or a change is interrupted; a state
  written by an earlier version has no `server_url` and is accepted as it is.
* **Status for the window.** A new `status.py` beside `state.py` holds
  `AgentStatus` and `StatusStore(path)`, which writes atomically (temporary
  file, `os.replace`). `AgentScheduler` takes an optional store; the poll and
  inventory ticks record success, and a failure of either records its
  `FailureKind` code, not the exception text: the window turns the code into a
  Russian sentence (R-17), and no raw text from a library is stored or shown.
  `run()` records `waiting` and `running`. The file sits next to the state
  file (`state_path.parent / "status.json"`), so it needs no new setting and
  inherits the folder's protection.

The agent's message about waiting goes to the same logging stream as every
other agent message. On Windows that stream is not persisted today; that is an
existing gap, not widened here, and the status file carries the reason as a code
so the window shows it in Russian.

### 1.2 Server: publish the authority (`warden_server`)

* `api/tls.py` (new router, `/api/v1/tls`) with `GET /ca`, open like
  `/health`. It reads `Settings.tls_ca_path` (`WARDEN_TLS_CA_PATH`) **at request
  time** and returns `{"pem", "sha256"}`. It takes only the first
  `-----BEGIN CERTIFICATE-----` block of the file, so a path mistakenly pointed
  at a file that also holds a private key can never return the key. The
  fingerprint is the SHA-256 of the block's DER form (`ssl.PEM_cert_to_DER_cert`,
  `hashlib`), as 64 lowercase hex characters. No path set, no file, or no
  certificate block: 404.
* Not written to the audit log: it is unauthenticated, public data, and a row
  per request would let an anonymous caller grow the table. `/health` is the
  precedent. D-13 says so.
* `schemas/tls.py` for the response; the router is included in `main.py`;
  `contracts/openapi.yaml` is regenerated with `server/scripts/export_openapi.py`.
* The test that lists open operations grows a fourth entry, and its docstring
  and D-10's sentence naming the open operations are updated (see 1.5).

### 1.3 Configurator (`warden_agent.configurator`, new package)

Nothing here branches on the operating system. The OS-specific parts sit in one
module named `windows.py`, the pattern `service/windows.py` already sets, and
the pure parts are tested anywhere.

| Module | Role | OS-specific |
|---|---|---|
| `messages.py` | Every string the window and the CLI show, in Russian, in one place | no |
| `paths.py` | `AgentPaths` (config, CA file, state, status, log) built from a directory | no |
| `config_file.py` | Reads the configuration with `tomllib`; rewrites it from a template with comments, keeping the keys an administrator already set (flat scalars) and writing paths as TOML literal strings | no |
| `logic.py` | The operations below | no |
| `controller.py` | The window's state machine: which buttons are enabled, what a result means; runs an operation through injected `run_async` / `post_to_ui` so tests drive it synchronously | no |
| `view.py` | The PySide6 window and its dialogs, thin over the controller; the only module that imports Qt | no (Qt is cross-platform) |
| `backend.py` | `Backend` protocol: `paths`, `is_elevated()`, `service_state()`, `restart_service()` | no |
| `__main__.py` | The generic CLI (`--check`, `--apply`) over explicit paths with a no-op backend, and `--gui`, a development aid that opens the window over such a folder so it can be run and looked at on any machine; it is not documented for users and no Linux package ships it | no |
| `windows.py` | `WindowsBackend` (`win32serviceutil`, `%ProgramData%`, elevation check) and `main()`: the entry the frozen exe runs; opens the window, or runs `--check` / `--apply` / `--selftest` (builds the window off screen and exits, so CI can prove the frozen exe starts) | yes |

**Operations in `logic.py`** (async, reusing `ServerClient` and `EnrollmentError`):

* `probe(server_url, ca_file=None, extra_ca_pem=None)`: `GET /api/v1/tls/ca` with the
  verifying context (not `/health`: behind the deployment's proxy only `/api/*`
  reaches the server, and `/health` is answered by the panel -- found by running the
  tool against a real stack). A reply counts as the server's if it is the authority
  or the 404 of a deployment without one, both JSON in the server's own shape. It sorts the outcome into *unreachable*, *certificate not trusted*
  (a `httpx.ConnectError` whose cause chain holds `ssl.SSLCertVerificationError`),
  *unexpected reply*, or *reachable and trusted* (R-3, A-6).
* `fetch_authority(server_url)`: the one request made without checking the
  certificate (R-9). It sends `GET /api/v1/tls/ca` and nothing else. The result
  is parsed locally and the server's own `sha256` field is ignored: the SHA-256 is
  computed here over the DER form, and subject and validity are read through a
  fresh `ssl.SSLContext.load_verify_locations(cadata=...)` and `get_ca_certs()`,
  which also rejects text that is not a certificate. It returns a `TrustOffer`
  or `NoAuthority` (404).
* `connect(...)`: the whole flow. Probe; if the certificate is not trusted and no
  authority was given, return `TrustNeeded(offer)`; the caller confirms and calls
  again with the authority and, in silent mode, the expected fingerprint, which
  must equal the computed one or the result is `FingerprintMismatch`. Enrollment
  runs over a context that already includes the candidate authority held in
  memory. **Only after it succeeds** are the files written, in this order: the
  authority file, the configuration, and the state file last, so the state file is
  the commit point (R-10, and the crash window is closed by the `server_url` check
  of 1.1). The token is never written anywhere. A failed enrollment writes nothing.
* `change_server` rules inside `connect`: an enrolled station given another
  server needs `replace=True`; the previous authority file is removed unless
  the new server uses the same one (R-11).
* `retrust(paths, offer)`: replaces the authority file for an enrolled station
  after a fingerprint confirmation, verified first with `/health` (A-15). It does
  not enroll again.
* `read_status(paths, backend)`: the view model for R-2.

**Actions are logged** (R-18) to `configurator.log` in the agent's folder: the
address, the fingerprint the administrator accepted, the outcome, and a server
change. Never the token.

**The window** (`view.py`, Russian, described in §6) starts with the current
address filled in from the configuration and the status block filled in from
`read_status`. Long operations run on a `QThread` that calls `asyncio.run`, and
the result comes back to the window through a Qt signal, so the window never
freezes. Every dialog is built with its button texts taken from `messages.py`,
never Qt's standard buttons, so nothing depends on Qt's translation files and
the whole surface stays Russian (R-17). Without
elevation (`is_elevated()` false) the fields are disabled and a banner says why
(R-12, A-9). The frozen exe also carries a manifest that asks for elevation, so
opening it from the Start menu shows the UAC prompt first.

**Paths.** `AgentPaths` follows the configuration: the agent reads its state from
`state_path`, which on Linux is not beside the configuration file, so the tool writes
the state there and reads the status file from beside it, and writes `state_path` into
the configuration when it is missing, since the agent's own default is relative to
where it is started.

**The CLI** (`--apply`) is what the installer calls, and it works on any
platform over `--config PATH`:

```
warden-agent-config --apply --server URL [--token T] [--ca-sha256 HEX]
                    [--replace] [--no-restart] [--config PATH]
warden-agent-config --check --server URL [--config PATH]
```

Exit 0 when the station is connected (or already was), 3 when it could not
connect; the reason is written to `configurator.log` because the windowed exe has
no console. `--ca-sha256` is the silent path's expected fingerprint: the authority
is accepted only if it matches, and without it an untrusted server is left
untrusted (R-14, A-3). `--replace` is passed by the installer when the person
running it gave a server, since that is the explicit confirmation R-11 asks for.
The generic CLI also delivers R-19's spirit for Linux: a station there can be
enrolled against a self-signed server without hand-editing anything.

### 1.4 Deployment and installer

* **`docker-compose.yml`.** The proxy's data volume also holds the authority's
  *private key* next to its certificate, so it is **not** mounted into the
  server. A small `ca-export` service (the same `caddy` image, which has a shell)
  mounts `caddy_data` read-only and a new `warden_ca` volume read-write, waits up
  to two minutes for `root.crt` to appear, copies just that file, and then idles.
  `server` mounts `warden_ca` read-only and gets
  `WARDEN_TLS_CA_PATH=/warden-ca/root.crt`. A deployment with a real
  certificate never creates `root.crt`; the wait ends, the volume stays empty and
  the endpoint answers 404, which is the "no authority of its own" case. No
  host port changes.
* **`Product.wxs`** (WiX v5, already referencing `WixToolset.UI.wixext`):
  a second file, `warden-agent-config.exe`, in the install folder; a Start menu
  shortcut «Warden Agent — настройка»; a custom dialog «Подключение к серверу»
  with `SERVER_URL`, `ENROLLMENT_TOKEN` and `SERVER_CA_SHA256`, placed in the wizard
  after the welcome page and skipped for an upgrade or a repair
  (`NOT Installed AND NOT WIX_UPGRADE_DETECTED`, R-13, R-16); the three properties
  are `Secure`, and the token `Hidden`, so a verbose installer log does not print
  it. A deferred, non-impersonated custom action `ApplyConnection` runs the
  exe with `--apply --replace --no-restart` after `InstallFiles` and before the
  service starts, so the service comes up already configured. `Return="ignore"`:
  a failed connection never fails the installation (R-13). The last wizard page
  has the option «Открыть настройку агента», which runs the exe as the
  installing user. The same three properties work for `msiexec /qn` (R-14).
* **`config.example.toml` for Windows** loses the `enrollment_token` placeholder
  and the placeholder `server_url`, so the window starts empty and `ca_file` is
  described in a comment.
* **`release.yml`**: a second `pyinstaller` step freezes
  `configurator/windows.py` with `--onedir --windowed --uac-admin --hidden-import
  win32timezone`. One directory rather than one file: the Qt libraries stay
  separate files a licensee can replace (PySide6 is LGPLv3), and a one-file build
  would unpack tens of megabytes into `%TEMP%` at every launch. `Product.wxs`
  installs that directory under a `Configurator` folder of the install folder with
  WiX's `Files` element, the shortcut pointing at the exe inside it, and
  `warden-agent.wixproj` takes the directory as one more preprocessor variable,
  the way the service exe's path is handed over. A notices file naming Qt and
  PySide6, their licence and where the source is obtained, ships with it. After
  freezing, the job runs the frozen exe with `--selftest` under
  `QT_QPA_PLATFORM=offscreen`, so a missing Qt plugin fails the build instead of
  the first administrator. The
  workflow also gains `workflow_dispatch` (with a fallback version and the upload
  step limited to tags), so the installer can be compiled from GitHub without
  publishing a release; without it any WiX mistake in this change would first
  show up on a real release tag, as the packaging history already did.

### 1.5 Constitution and documents

* **Constitution 1.5.0 (MINOR), decision D-13**: an agent is connected from a
  window or the installer; it trusts the server's own authority only through a
  fingerprint the administrator compares, for the agent alone and never for the
  system; the token is not kept; the server publishes its authority openly.
  D-10's sentence that names the operations reachable without a credential is
  widened to name this fourth one. Section II's table of agent modules gains
  `warden_agent.configurator` (connection window and CLI; PySide6 in the window
  only). Principle text is unchanged.
* **Section V boundaries** added: the first trust rests on a human comparing a
  fingerprint; the window exists only on Windows; the token is visible on the
  installer helper's command line during an install that carries it, and in
  command-line auditing if the organization has it on; the authority lasts ten
  years and is not rotated by anything, and the fingerprint in the panel
  protects against interception between station and server, not against a
  compromised server; the request for the authority is not audited.
* **`docs/ru` (canonical) and `docs/en`**: `usage.md` gets the Windows install
  through the wizard and silently, the window, the fingerprint comparison, changing
  server, and an honest-status paragraph; `architecture.md` gets a section on the
  trust model and the new endpoint; the boundaries are mirrored.

### 1.6 Panel

`web/src/api/client.ts` gets `getTlsAuthority()` (no token, since the endpoint is
open); `types.ts` a `TlsAuthority` type; a small `lib/fingerprint.ts` formats
64 hex characters as `AB:CD:…`; `web/src/pages/AgentsPage.tsx` shows the block
described in §6 to the same role that sees «Выпустить токен».

## 2. Alternatives considered

| Option | Why rejected |
|---|---|
| Put the server's authority into the Windows machine store | Trust would become system-wide: anyone holding the authority's key could impersonate any site to every program on the station. Spec R-7 forbids it, and it needs the certificate store API and a rollback on uninstall |
| Turn certificate checking off (`verify=False`), or trust the server's leaf certificate on first use | The first breaks principle 5. The leaf of a `tls internal` certificate is reissued every 12 hours, so a pinned leaf would fail by the next day; only the root, which lasts ten years, is a stable anchor |
| Mount the proxy's whole data volume read-only into the server | Simplest, but the volume holds the authority's private key, and the server is the component exposed to the network. Copying only `root.crt` through a sidecar keeps the key out of the API container |
| Serve `root.crt` straight from the proxy | Sits outside `contracts/openapi.yaml` (principle 11), and the panel would have to hash the file in the browser to show a fingerprint |
| Let the service enroll at first start with the token in the configuration | Leaves a live secret on disk (R-10), and reports a wrong token only in a log nobody reads |
| A local web page served by the agent | The agent must not listen (D-1) and it would add a local attack surface for one screen of settings |
| tkinter | Standard library and small, but it needs a real display to be tested (skipped on a CI runner without one) and is not even installed in this Mac's Python, so the window would be checked only on the Windows leg and by hand; its look and high-DPI scaling on Windows 10/11 are also poorer. The maintainer chose PySide6 |
| wxPython instead of Qt | No advantage for one screen, and no equivalent of `pytest-qt` for driving it headlessly |
| The full `PySide6` distribution | The window needs only the core, gui and widgets modules, which `PySide6-Essentials` carries at a fraction of the size |
| A one-file frozen window | Bundles Qt into a single archive that unpacks to `%TEMP%` on every start (slow, and antivirus-prone), and hides the LGPL libraries from anyone who would replace them |
| Verify the fingerprint by having the administrator paste the whole certificate | More error-prone than comparing a 95-character string, and gives no advantage: the fingerprint of what is pasted is what gets compared either way |

## 3. Constitution compliance

| Principle | How it is satisfied |
|---|---|
| 1. Platform code is isolated | The elevation check, the service restart, the `%ProgramData%` path and the `win32serviceutil` import are only in `configurator/windows.py`, matched by the existing per-file ruff exemption for `windows.py`. `logic.py`, `controller.py`, `view.py`, `config_file.py`, `__main__.py`, `core/transport.py` and `status.py` contain no `sys.platform`, `platform.system` or Windows import; Qt is imported only by `view.py` and is a cross-platform toolkit, not an OS-specific library, and `ssl` is standard library. The system store is loaded by `ssl.create_default_context()` itself, not by code that branches. The frozen entry point injects the Windows backend, like `service/windows.py`. `grep` for `sys.platform`/`platform.system` outside `collectors/registry.py` stays empty |
| 2. Data does not leave the buffer without a request | Untouched. The new traffic is the trust step and enrollment; no event is sent, and the scheduler's collection loop still has no push |
| 3, 4. Window cap, buffer retention | Untouched |
| 5. Authenticated and encrypted | The token-for-key exchange, the stored hash of the key and TLS are unchanged. The trust anchor is extended by one authority that the administrator confirmed by fingerprint. The one unverified request (`fetch_authority`) carries no token and no key; the enrollment and every later request use the verifying context. A test records every request of the flow and fails if the token or the key rides an unverified one (A-18) |
| 6. Inventory versioned | Untouched |
| 7. Testable without hardware | The logic runs over `tmp_path`, `httpx.MockTransport`, and a real TLS server on localhost using certificates made by `trustme`; the controller over injected stand-ins; the Windows backend over stand-in `win32` modules, as `test_windows_service.py` does. The window itself is driven with `pytest-qt` under Qt's offscreen platform, on every CI leg and on this Mac. Only how it looks on a real Windows, the wizard, elevation and the real service restart need Windows, and they are listed in §8 as manual |
| 8. Every action is logged | The configurator writes trust decisions (with the accepted fingerprint), enrollment attempts and outcomes, and server changes to `configurator.log`, never the token (A-14); the server's `agent.enroll` audit entry is unchanged. The public read of the authority is deliberately not audited (see 1.2) |
| 9. Language mode | Window, wizard, and every error in Russian from one catalog (`messages.py`), with a test that each string contains Cyrillic and a walk over every widget and dialog of the window that finds no other visible text (A-17); comments and docstrings in English; `docs/ru` canonical and `docs/en` in step; specs in English |
| 10. Honesty about boundaries | Section V boundaries listed in 1.5, and an honest-status paragraph in `docs/*/usage.md` naming what only a real Windows 10/11 run can prove (wizard, window, UAC, service restart) |
| 11. The contract is the source of truth | The endpoint is added to `contracts/openapi.yaml` by regeneration; the equality test covers it; an agent integration test feeds the real server app's reply into `fetch_authority`'s parser, so the two sides are checked against each other |
| D-1 Active agent | Every connection the window makes is outbound; nothing listens |
| D-3 Enrollment | Same token-for-key exchange, made from the window |
| D-7 Native installer | Extends the `.msi`: second exe, wizard page, shortcut |
| D-10 Roles and open operations | The list of operations open without a credential grows by one; the test that enforces it is updated in the same change and D-10's sentence is amended (1.5) |

**Violations:** none. The change to D-10's wording and the new decision go
through Section VII as a MINOR amendment, 1.5.0.

## 4. Affected modules

| Module | Change |
|---|---|
| `agent/src/warden_agent/config.py` | `ca_file` |
| `agent/src/warden_agent/state.py` | `server_url` |
| `agent/src/warden_agent/status.py` | new: `AgentStatus`, `StatusStore` |
| `agent/src/warden_agent/core/transport.py` | `build_ssl_context`, `verify` parameter |
| `agent/src/warden_agent/core/scheduler.py` | optional status store |
| `agent/src/warden_agent/__main__.py` | `NotConfiguredError`, waiting loop, context, reload callable |
| `agent/src/warden_agent/service/windows.py` | pass the reload callable |
| `agent/src/warden_agent/configurator/` | new package (§1.3) |
| `agent/pyproject.toml` | new `gui` extra with `PySide6-Essentials`, included in `dev`; `pytest-qt` and `trustme` in `testing`; script entry for the generic CLI |
| `.github/workflows/ci.yml` | on the Linux agent leg, install the system libraries Qt's offscreen platform needs |
| `agent/tests/unit/test_main/test_enroll_if_needed.py` | the missing-token case now expects `NotConfiguredError` |
| `agent/tests/unit/test_{config,state,transport,scheduler,status,configurator}/` | new and extended tests |
| `agent/tests/integration/test_full_cycle/` | authority reply against the real server app; TLS enrollment against a local server |
| `server/src/warden_server/api/tls.py`, `schemas/tls.py`, `config.py`, `main.py` | endpoint, schema, `tls_ca_path`, router |
| `server/tests/integration/test_tls_authority/` | new; `test_roles/test_open_endpoints.py` updated |
| `contracts/openapi.yaml` | regenerated |
| `web/src/api/{client,types}.ts`, `web/src/lib/fingerprint.ts`, `web/src/pages/AgentsPage.tsx` | fingerprint block; `vitest` tests |
| `docker-compose.yml` | `ca-export` service, `warden_ca` volume, server mount and variable |
| `packaging/windows/{Product.wxs,warden-agent.wixproj,config.example.toml}` | second exe, shortcut, wizard page, custom action, template |
| `.github/workflows/release.yml` | freeze the configurator; `workflow_dispatch` |
| `.specify/memory/constitution.md` | D-13, D-10 wording, Section V, 1.5.0 |
| `docs/ru/{usage,architecture}.md`, `docs/en/{usage,architecture}.md` | described in 1.5 |

## 5. Data formats

**`GET /api/v1/tls/ca`** (no credential): `200 {"pem": "-----BEGIN CERTIFICATE-----\n…", "sha256": "<64 lowercase hex>"}`;
`404 {"detail": …}` when the server has no authority of its own. Added to
`contracts/openapi.yaml`.

**Agent configuration**, one new key, `ca_file` (a path, TOML literal string on
Windows). After the window enrolls a station the file holds `server_url`,
`ca_file` when one was trusted, the intervals, retention, and the two paths,
and **no** `enrollment_token`.

**`state.json`**: `{"agent_id", "agent_key", "server_url"}`; the third key is new
and optional on read.

**`status.json`**: `{"state": "running" | "waiting", "detail": "not_configured" |
"server_changed" | "ca_unreadable" | null, "last_success_at": ISO | null,
"last_error": "unreachable" | "certificate_not_trusted" | "credential_refused" |
"server_error" | "other" | null, "last_error_at": ISO | null}`. Codes, not text; the
window owns the Russian wording.

**Files in the agent's folder**: `server-ca.pem` (the trusted authority),
`status.json`, `configurator.log`, next to the existing configuration, state and
buffer, all under the folder's protected permissions (R-8).

**Fingerprint for people**: the 64 hex characters in upper case, in pairs joined
by colons. The window and the panel use the same form; comparison ignores case,
colons and spaces.

**Installer properties**: `SERVER_URL`, `ENROLLMENT_TOKEN` (hidden),
`SERVER_CA_SHA256`; e.g. `msiexec /i warden-agent.msi /qn SERVER_URL=https://…
ENROLLMENT_TOKEN=… SERVER_CA_SHA256=AB:CD:…`.

## 6. Interface

**Window «Warden Agent — настройка»**

```
Подключение к серверу
  Адрес сервера        [ https://…                       ]
  Токен регистрации    [ ••••••••                        ]
  [ Проверить соединение ]   [ Подключить ]

Состояние
  Служба:            работает | остановлена | не установлена
  Станция:           зарегистрирована на https://… | не зарегистрирована
  Последний обмен:   25.09.2026, 13:17  (или «ещё не было»)
  Последняя ошибка:  …
```

Trust dialog, shown only when the certificate is not trusted and the server
offers an authority: «Сервер использует собственный центр сертификации»,
«Кем выдан», «Действителен до», «Отпечаток SHA-256», the line «Сверьте отпечаток с
показанным в панели, раздел «Станции»», and the buttons «Доверять и подключить»
and «Отмена». A second dialog confirms a server change and names what is
forgotten. For an enrolled station whose server can no longer be verified, the
status block offers «Доверять новому сертификату» instead of asking for a token.
Without administrator rights: a banner «Нужны права администратора», the fields
disabled.

**Installer wizard**: a page «Подключение к серверу» with the three fields, all
optional, and the hint that they can be filled in later from the Start menu; on
the last page the option «Открыть настройку агента».

**Panel, «Станции»**: beside «Выпустить токен», for the roles that see it, a
block «Отпечаток сертификата сервера (SHA-256)» with the formatted value and the
line «Сверьте его с отпечатком в окне настройки агента». When the endpoint
answers 404 the block says «Сервер использует сертификат, который система уже
проверяет: сверять отпечаток не нужно». No other screen changes.

## 7. Risks

| Risk | Mitigation |
|---|---|
| The WiX changes (custom dialog, deferred action with a formatted command line, the exit-page option) cannot be built or run here; the packaging history shows several fixes after the first real build | `workflow_dispatch` compiles the installer on GitHub without a release; §8 lists the manual Windows pass; the docs say plainly that it is unverified until then |
| The first trust is only as good as the comparison: an administrator who clicks through defeats it, and an attacker in the path at that moment could feed a false authority | The dialog puts the fingerprint next to the instruction to compare; a silent install cannot trust anything without the expected fingerprint; the boundary is stated in Section V and the docs |
| The token is on the helper's command line for the moments of a silent install | It is one-time and useless once used; the installer hides it in its own log; the residual exposure to command-line auditing is stated as a boundary. Passing it another way (a file, stdin) would leave a file or need a custom action type WiX does not offer |
| `--windowed` gives the exe no console, so `--apply` failures are invisible | Every outcome goes to `configurator.log`, and the window shows the same state when opened |
| The server rebuilt with a new authority breaks enrolled stations until each is re-trusted by hand | The window detects it and offers the new authority (A-15); automatic rotation is out of scope in the spec and named in Section V |
| Qt makes the configurator large (tens of megabytes) and brings LGPLv3 obligations | `PySide6-Essentials` only, and a one-directory freeze so the Qt libraries stay replaceable files; a notices file ships with the installer; the size is measured on the first CI build and reported in the documentation |
| Qt's offscreen platform needs system libraries the Linux CI leg may lack | The leg installs them (`libegl1`, `libgl1`, `libxkbcommon0`, `libdbus-1-3`); the window tests use `pytest.importorskip("PySide6.QtWidgets")`, so a missing library skips them there rather than failing, and the Windows leg still runs them |
| A Qt plugin is missed by the freeze and the frozen window does not start | PyInstaller's PySide6 hook collects the plugins; the release job runs the frozen exe with `--selftest`, which builds the window off screen and exits, so the build fails instead of the first administrator |
| The waiting loop hides a permanently unconfigured service | The status file and the window report `waiting` with the reason; the message is also logged each cycle |

## 8. Verification plan

**In CI, no Windows hardware (principle 7):**

```bash
cd agent  && ruff check . && ruff format --check . && mypy src && bandit -c pyproject.toml -r src && pytest
cd server && ruff check . && ruff format --check . && mypy src alembic && bandit -c pyproject.toml -r src \
  && pytest --cov=warden_server --cov-fail-under=80 && diff-cover coverage.xml --compare-branch=origin/main --fail-under=80
cd web    && npm run lint && npm run format && npm test && npm run build
```

What the tests cover, by acceptance criterion:

* **A-1, A-2, A-3, A-4, A-5, A-6, A-7, A-8, A-11, A-14, A-18**: `agent/tests/unit/test_configurator/`.
  A `trustme` authority signs a certificate for a real TLS server on localhost
  running in a thread, so verification, refusal, and the trust step are real
  handshakes. `httpx.MockTransport` stands in where TLS is not the point.
  A-8 lists the files under a `tmp_path` folder before and after, and no code path
  touches a system store. A-18 records every request the flow makes.
* **A-10**: `agent/tests/unit/test_main/` (waiting, then configured) with an
  injected clock and reload callable.
* **A-12, A-13**: `server/tests/integration/test_tls_authority/` (fingerprint equals
  the hash of the certificate; no path, no file, or no certificate block gives
  404; a file that also holds a key returns only the certificate), plus the
  open-operations test and the contract-equality test; the panel's block is a
  `vitest` test.
* **A-15**: `retrust` after the test server's authority is replaced.
* **A-16**: existing suites, with an enrolled state that has no `server_url` and
  a configuration that carries a token.
* **A-17**: a test over `messages.py`.
* `controller.py` over stand-ins, and `windows.py` over stand-in `win32` modules.
* `view.py` with `pytest-qt` under `QT_QPA_PLATFORM=offscreen`, on every leg: types
  an address and a token, presses «Подключить» over a stub controller, and checks
  that the trust dialog shows the fingerprint and both buttons, that the banner and
  the disabled fields appear without elevation, and that the status block shows
  what `read_status` returns. A walk over every widget and dialog text checks the
  whole surface is Russian (A-17). A screenshot (`QWidget.grab()`) of each state is
  kept as a CI artifact for whoever does the manual pass.
* The release workflow freezes both exes, runs the frozen window's `--selftest`, and
  compiles the installer.

**End to end on this Mac, on a throwaway Compose project** (ports 8443/8080,
never the tracked ports, the user's `gitlab` container untouched):
`GET /api/v1/tls/ca` returns the proxy's root and its fingerprint, equal to
`openssl x509 -fingerprint -sha256` of `root.crt`; the key is not reachable from
the server container; the panel's block equals the CLI's; then
`python -m warden_agent.configurator --apply` with a matching, a wrong, and no
fingerprint, and `python -m warden_agent` polling through the verified
connection, and `status.json` moving. The window is opened over the same folder
with `python -m warden_agent.configurator --gui` and photographed, which checks the
layout and the flow on this Mac (the look on Windows still needs Windows).

**Manual, on a real Windows 10/11 (constitution Section VI, A-19), before a
release, and recorded honestly in `docs/*/usage.md`:** the wizard with and
without values; a silent install with the three properties; an upgrade over an
enrolled station; the Start menu entry and its elevation prompt; the window's
appearance and the trust dialog; the service restart; that the machine's
certificate store is unchanged. Until it is done, the documentation says the
Windows installer and window are checked only by compilation and by the logic
tests above.
