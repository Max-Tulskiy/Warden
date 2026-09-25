"""The command line the installer calls, and that works on any platform."""

import asyncio
import json

import pytest

from warden_agent.configurator.__main__ import main
from warden_agent.configurator.backend import LocalBackend, ServiceState
from warden_agent.configurator.cli import EXIT_CONNECTED, EXIT_NOT_CONNECTED, run_cli
from warden_agent.configurator.logic import fetch_authority
from warden_agent.configurator.paths import AgentPaths
from warden_agent.state import AgentState

CODE = "s3cret-enrollment-token"


class _Backend(LocalBackend):
    def __init__(self, paths):
        super().__init__(paths)
        self.restarts = 0

    def restart_service(self) -> None:
        self.restarts += 1


@pytest.fixture
def backend(tmp_path) -> _Backend:
    return _Backend(AgentPaths.for_directory(tmp_path))


@pytest.fixture
def server(tls_server):
    tls_server.answer("GET", "/health", body={"status": "ok"})
    tls_server.on(
        "POST",
        "/api/v1/enroll",
        lambda request: (
            (201, {"agent_id": "a1", "agent_key": "k1"})
            if json.loads(request.body)["token"] == CODE
            else (400, {"detail": "bad"})
        ),
    )
    tls_server.on(
        "GET",
        "/api/v1/tls/ca",
        lambda _request: (200, {"pem": tls_server.authority_pem}),
    )
    return tls_server


def _fingerprint(server) -> str:
    """The command line runs its own event loop, so these tests are synchronous."""
    return asyncio.run(fetch_authority(server.url)).fingerprint


def _run(backend, *arguments) -> int:
    return run_cli(list(arguments), backend)


def test_apply_with_the_expected_fingerprint_connects_and_restarts_the_service(
    server, backend, capsys
):
    fingerprint = _fingerprint(server)

    code = _run(
        backend, "--apply", "--server", server.url, "--token", CODE,
        "--ca-sha256", fingerprint,
    )  # fmt: skip

    assert code == EXIT_CONNECTED
    assert AgentState.load(backend.paths.state).is_enrolled
    assert backend.restarts == 1
    assert server.url in capsys.readouterr().out


def test_the_installers_helper_does_not_restart_a_service_not_started_yet(
    server, backend
):
    fingerprint = _fingerprint(server)

    _run(
        backend, "--apply", "--no-restart", "--server", server.url, "--token", CODE,
        "--ca-sha256", fingerprint,
    )  # fmt: skip

    assert backend.restarts == 0
    assert AgentState.load(backend.paths.state).is_enrolled


def test_apply_without_a_fingerprint_trusts_nothing_and_says_what_to_compare(
    server, backend, capsys
):
    fingerprint = _fingerprint(server)

    code = _run(backend, "--apply", "--server", server.url, "--token", CODE)

    assert code == EXIT_NOT_CONNECTED
    assert not AgentState.load(backend.paths.state).is_enrolled
    assert not backend.paths.authority.exists()
    assert fingerprint in capsys.readouterr().out
    assert backend.restarts == 0


def test_apply_with_the_wrong_fingerprint_is_refused(server, backend, capsys):
    code = _run(
        backend, "--apply", "--server", server.url, "--token", CODE,
        "--ca-sha256", "ab" * 32,
    )  # fmt: skip

    assert code == EXIT_NOT_CONNECTED
    assert not backend.paths.authority.exists()
    assert "ab" * 32 in capsys.readouterr().out


def test_apply_over_a_station_already_connected_does_nothing_and_succeeds(
    server, backend
):
    fingerprint = _fingerprint(server)
    arguments = (
        "--apply", "--server", server.url, "--token", CODE, "--ca-sha256", fingerprint
    )  # fmt: skip
    _run(backend, *arguments)
    backend.restarts = 0

    code = _run(backend, *arguments)

    assert code == EXIT_CONNECTED
    assert backend.restarts == 0


def test_moving_an_enrolled_station_needs_replace(server, backend):
    AgentState(
        agent_id="old", agent_key="oldkey", server_url="https://old.example"
    ).save(backend.paths.state)
    fingerprint = _fingerprint(server)
    arguments = (
        "--apply", "--server", server.url, "--token", CODE, "--ca-sha256", fingerprint
    )  # fmt: skip

    without = _run(backend, *arguments)
    with_replace = _run(backend, *arguments, "--replace")

    assert without == EXIT_NOT_CONNECTED
    assert with_replace == EXIT_CONNECTED
    assert AgentState.load(backend.paths.state).agent_id == "a1"


def test_nothing_printed_holds_the_token(server, backend, capsys):
    fingerprint = _fingerprint(server)

    _run(
        backend, "--apply", "--server", server.url, "--token", CODE,
        "--ca-sha256", fingerprint,
    )  # fmt: skip
    _run(backend, "--apply", "--server", server.url, "--token", CODE)

    captured = capsys.readouterr()
    assert CODE not in captured.out + captured.err


def test_check_reports_each_state_and_succeeds_only_when_trusted(
    server, backend, unreachable_url, capsys
):
    untrusted = _run(backend, "--check", "--server", server.url)
    unreachable = _run(backend, "--check", "--server", unreachable_url)
    fingerprint = _fingerprint(server)
    _run(
        backend, "--apply", "--server", server.url, "--token", CODE,
        "--ca-sha256", fingerprint,
    )  # fmt: skip
    capsys.readouterr()
    trusted = _run(backend, "--check", "--server", server.url)

    assert (untrusted, unreachable, trusted) == (
        EXIT_NOT_CONNECTED,
        EXIT_NOT_CONNECTED,
        EXIT_CONNECTED,
    )
    assert "доверен" in capsys.readouterr().out


def test_the_local_backend_has_no_service_and_asks_nothing_of_the_machine(tmp_path):
    backend = LocalBackend(AgentPaths.for_directory(tmp_path))

    assert backend.service_state() is ServiceState.NOT_APPLICABLE
    assert backend.is_elevated()
    backend.restart_service()  # does nothing, and does not fail


def test_apply_and_check_need_a_server(backend, capsys):
    with pytest.raises(SystemExit) as excited:
        _run(backend, "--apply")

    assert excited.value.code == 2
    assert "--server" in capsys.readouterr().err


def test_the_tool_needs_to_be_told_which_configuration_to_work_on(capsys):
    with pytest.raises(SystemExit) as refused:
        main(["--check", "--server", "https://a.example"])

    assert refused.value.code == 2
    assert "--config" in capsys.readouterr().err
