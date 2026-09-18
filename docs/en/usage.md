# Deployment and usage guide

The canonical text is in Russian; see [../ru/usage.md](../ru/usage.md).

## Deploying the server

Requires Docker and Docker Compose.

```bash
cp .env.example .env
# edit .env: POSTGRES_PASSWORD, WARDEN_JWT_SECRET,
# WARDEN_SEED_ADMIN_USERNAME/PASSWORD, WARDEN_DOMAIN
docker compose up --build -d
```

What happens:

1. PostgreSQL starts and waits for its healthcheck.
2. The server applies Alembic migrations and starts; if
   `WARDEN_SEED_ADMIN_USERNAME`/`WARDEN_SEED_ADMIN_PASSWORD` are set and the
   database has no operator yet, a first administrator account is created.
3. The web panel is built and started.
4. Caddy obtains a (self-signed, for `localhost`) TLS certificate and proxies
   `/api/*` to the server, everything else to the panel.

The panel is reachable at `https://localhost/` (the browser will warn about
the self-signed certificate -- expected for a local/self-hosted deployment;
point `WARDEN_DOMAIN` at a real domain instead and Caddy will obtain a real
Let's Encrypt certificate automatically).

**Change the administrator password after first login** and remove
`WARDEN_SEED_ADMIN_USERNAME`/`WARDEN_SEED_ADMIN_PASSWORD` from `.env` -- the
bootstrap only creates an account when there is no operator at all yet, so a
later container restart with the same variables changes nothing, but there
is no reason to keep a production password sitting in `.env` in the clear
longer than needed.

## Enrolling an agent

1. Log in to the panel and issue an enrollment token (from the panel, or
   directly: `POST /api/v1/enrollment-tokens` with an
   `Authorization: Bearer <JWT>` header).
2. On the workstation, put that token in the agent config's
   `enrollment_token` field before the first start. Until that field is
   removed, the config carries a live one-time secret -- handle it like
   one. Packages install `/etc/warden-agent/config.toml` at mode `0600`
   inside a `0700` directory (Linux) and restrict the file to the
   SYSTEM/Administrators accounts (Windows, unverified -- no test
   machine).
3. Once enrolled, the agent saves its issued key to `state.json` -- the
   config's `enrollment_token` line must then be deleted by hand, it does
   not disappear on its own and is no longer needed.

## Installing the agent

### Windows 10/11 (`.msi`)

Download the `.msi` from the release page and run it as an administrator. It
installs the "Warden Insider-Activity Monitoring Agent" service (auto-start)
and a default configuration at
`%ProgramData%\Warden\agent\config.toml` -- edit it (server address,
enrollment token) and restart the service:

```powershell
Restart-Service WardenAgent
```

> The installer is unsigned -- SmartScreen will warn on first run
> (constitution Section V).

### Linux (`.deb` / `.rpm`)

```bash
# Debian/Ubuntu
sudo dpkg -i warden-agent_<version>_amd64.deb

# Fedora/RHEL and derivatives (ALT included)
sudo rpm -i warden-agent-<version>.x86_64.rpm
```

Both packages place the config at `/etc/warden-agent/config.toml` along with
a systemd unit. Edit the config, then enable the service:

```bash
sudo systemctl enable --now warden-agent
```

### From source (`pip`)

```bash
cd agent
pip install -e ".[dev]"
python -m warden_agent --config ./config.example.toml
```

## Verification without real hardware

Per constitution principle 7, server logic and the agent buffer are checked
by unit and integration tests with no flash drive, printer, or elevated
privileges needed:

```bash
cd server && pytest         # a test database (SQLite), no real PostgreSQL needed
cd agent && pytest          # buffer on a temp file, collectors against fixtures
cd web && npm test
```

A separate CI job (`server-postgres-smoke` in `ci.yml`) runs migrations and a
server startup against a real PostgreSQL instance -- this has also been
checked by hand: the full cycle (`docker compose up` → log in → issue a
token → enroll an agent → the station shows up in the list) was run end to
end against the real stack while preparing this release.

## Honest status of live platform-collector verification

Constitution Section VI requires more than passing unit tests -- at least one
live check of platform-specific code on a real system. As of this release:

| Platform | What has been checked live |
|---|---|
| Linux | All five collectors, on the development machine: real `dpkg`/`psutil` data (inventory), a real subprocess and a real `psutil`-observed process (processes), temporary SQLite files matching the Chrome/Firefox schema (websites). The full `.deb`/`.rpm` build via `nfpm` from an actually-frozen PyInstaller binary was run and the packages' contents inspected. |
| Windows | **Not checked live** -- there is no Windows machine on the development side. The code is written against the documented APIs (`pywin32`, `winreg`, `win32evtlog`) and type-checked; all of the *parsing logic* (`parse_uninstall_entries`, `parse_print_event_xml`, the device diff) is unit-tested on fixtures on any platform. CI (`ci.yml`, the `agent-test` job) genuinely runs the `test_*_windows_live.py` tests on a `windows-latest` runner -- the first real exercise of the `pywin32`/`winreg` calls, not just a code read-through. The `.msi` build (`release.yml`) is likewise built for real only in CI, on the first tag push, not verified locally beforehand. |

This is not an oversight -- it follows directly from constitution principle
10 ("honesty about boundaries"): naming the actual level of confidence beats
leaving the impression that both platforms were checked equally.
