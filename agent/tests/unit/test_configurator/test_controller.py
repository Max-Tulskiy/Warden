"""The window's behaviour, without a window.

The controller holds what the window shows and decides what each button does.
Its executor is synchronous here, so a click runs to its end before the next
line of the test, and the shared TLS server stands in for the real one.
"""

import asyncio
import json
import re
from datetime import UTC, datetime

import pytest

from warden_agent.configurator import messages
from warden_agent.configurator.backend import LocalBackend, ServiceState
from warden_agent.configurator.controller import WindowController
from warden_agent.configurator.paths import AgentPaths
from warden_agent.core.transport import FailureKind
from warden_agent.state import AgentState
from warden_agent.status import StatusStore

CODE = "s3cret-enrollment-token"
CYRILLIC = re.compile("[А-Яа-яЁё]")


class _SyncExecutor:
    def run(self, factory, on_done) -> None:
        try:
            result = asyncio.run(factory())
        except BaseException as exc:  # handed to the controller, as a thread would
            on_done(exc)
        else:
            on_done(result)


class _DeferredExecutor:
    """Holds the work until the test lets it finish."""

    def __init__(self) -> None:
        self.pending = []

    def run(self, factory, on_done) -> None:
        self.pending.append((factory, on_done))

    def finish(self) -> None:
        factory, on_done = self.pending.pop(0)
        on_done(asyncio.run(factory()))


class _Backend(LocalBackend):
    def __init__(self, paths, *, elevated=True, service=ServiceState.RUNNING):
        super().__init__(paths)
        self.elevated = elevated
        self.service = service
        self.restarts = 0

    def is_elevated(self) -> bool:
        return self.elevated

    def service_state(self) -> ServiceState:
        return self.service

    def restart_service(self) -> None:
        self.restarts += 1


@pytest.fixture
def paths(tmp_path) -> AgentPaths:
    return AgentPaths.for_directory(tmp_path)


@pytest.fixture
def backend(paths) -> _Backend:
    return _Backend(paths)


@pytest.fixture
def controller(backend) -> WindowController:
    return WindowController(backend, _SyncExecutor())


@pytest.fixture
def server(tls_server):
    tls_server.answer("GET", "/api/v1/agents/a1/tasks", body=[])
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


def _fill(controller, address, token=CODE):
    controller.set_address(address)
    controller.set_token(token)


def test_without_administrator_rights_the_window_says_so_and_does_nothing(
    paths, server
):
    backend = _Backend(paths, elevated=False)
    controller = WindowController(backend, _SyncExecutor())
    _fill(controller, server.url)

    controller.connect()
    controller.check()

    assert controller.state.banner == messages.BANNER_NOT_ADMIN
    assert not controller.state.fields_enabled
    assert not controller.state.can_connect
    assert server.requests == []


def test_connecting_needs_an_address(controller):
    assert not controller.state.can_connect

    controller.set_address("  ")
    assert not controller.state.can_connect

    controller.set_address("https://warden.example.internal")
    assert controller.state.can_connect


def test_an_untrusted_server_asks_for_trust_and_declining_stores_nothing(
    controller, server, paths
):
    _fill(controller, server.url)

    controller.connect()

    assert controller.state.pending_trust is not None
    assert controller.state.pending_trust.pem.strip() == server.authority_pem.strip()
    assert not paths.authority.exists()

    controller.answer_trust(False)

    assert controller.state.pending_trust is None
    assert controller.state.message == messages.TRUST_NOT_GIVEN
    assert controller.state.message_is_error
    assert not AgentState.load(paths.state).is_enrolled


def test_accepting_the_offer_connects_restarts_the_service_and_forgets_the_token(
    controller, server, backend, paths
):
    _fill(controller, server.url)
    controller.connect()

    controller.answer_trust(True)

    assert controller.state.message == messages.CONNECTED.format(server=server.url)
    assert not controller.state.message_is_error
    assert AgentState.load(paths.state).is_enrolled
    assert backend.restarts == 1
    assert controller.state.token == ""
    assert controller.state.status is not None and controller.state.status.enrolled


def test_a_refused_token_keeps_the_field_so_it_can_be_corrected(controller, server):
    typed = "wrong"
    _fill(controller, server.url, token=typed)
    controller.connect()

    controller.answer_trust(True)

    assert controller.state.message_is_error
    assert messages.ENROLLMENT_REFUSED.format(detail="bad") == controller.state.message
    assert controller.state.token == typed


def test_moving_an_enrolled_station_asks_first_and_declining_changes_nothing(
    controller, server, paths
):
    AgentState(
        agent_id="old", agent_key="oldkey", server_url="https://old.example"
    ).save(paths.state)
    _fill(controller, server.url)

    controller.connect()

    assert controller.state.pending_replace == "https://old.example"
    controller.answer_replace(False)
    assert controller.state.pending_replace is None
    assert AgentState.load(paths.state).agent_id == "old"


def test_accepting_the_move_goes_on_to_trust_and_then_enrolls(
    controller, server, paths
):
    AgentState(
        agent_id="old", agent_key="oldkey", server_url="https://old.example"
    ).save(paths.state)
    _fill(controller, server.url)
    controller.connect()

    controller.answer_replace(True)
    assert controller.state.pending_trust is not None
    controller.answer_trust(True)

    assert AgentState.load(paths.state).agent_id == "a1"
    assert AgentState.load(paths.state).server_url == server.url


def test_checking_an_address_says_what_was_found(controller, server, unreachable_url):
    controller.set_address(server.url)
    controller.check()
    assert controller.state.message == messages.CHECK_UNTRUSTED

    controller.set_address(unreachable_url)
    controller.check()
    assert controller.state.message == messages.CHECK_UNREACHABLE.format(
        server=unreachable_url
    )


def test_the_status_block_shows_the_service_the_station_and_the_last_contact(
    backend, paths
):
    AgentState(agent_id="a1", agent_key="k1", server_url="https://a.example").save(
        paths.state
    )
    when = datetime(2026, 9, 25, 10, 17, tzinfo=UTC)
    StatusStore(paths.status, now=lambda: when).record_success()

    controller = WindowController(backend, _SyncExecutor())
    lines = dict(controller.state.status_lines)

    assert lines[messages.LABEL_SERVICE] == messages.SERVICE_RUNNING
    assert lines[messages.LABEL_STATION] == messages.STATION_ENROLLED.format(
        server="https://a.example"
    )
    assert lines[messages.LABEL_LAST_CONTACT] == when.astimezone().strftime(
        "%d.%m.%Y, %H:%M"
    )
    assert lines[messages.LABEL_LAST_ERROR] == messages.LAST_ERROR_NONE


def test_a_station_never_heard_from_says_so_and_a_failure_is_in_words(backend, paths):
    store = StatusStore(paths.status)
    store.record_failure(FailureKind.UNREACHABLE)

    lines = dict(WindowController(backend, _SyncExecutor()).state.status_lines)

    assert lines[messages.LABEL_LAST_CONTACT] == messages.LAST_CONTACT_NEVER
    assert lines[messages.LABEL_LAST_ERROR] == messages.ERROR_UNREACHABLE


def test_a_waiting_agent_says_why(backend, paths):
    StatusStore(paths.status).record_waiting("not_configured")

    lines = dict(WindowController(backend, _SyncExecutor()).state.status_lines)

    assert lines[messages.LABEL_AGENT] == messages.WAITING_NOT_CONFIGURED


def test_the_address_from_the_configuration_fills_the_field(backend, paths):
    paths.config.write_text('server_url = "https://a.example"\n')

    assert (
        WindowController(backend, _SyncExecutor()).state.address == "https://a.example"
    )


def test_a_station_that_cannot_verify_its_server_offers_to_trust_the_new_authority(
    backend, paths, server
):
    AgentState(agent_id="a1", agent_key="k1", server_url=server.url).save(paths.state)
    StatusStore(paths.status).record_failure(FailureKind.CERTIFICATE_NOT_TRUSTED)
    controller = WindowController(backend, _SyncExecutor())
    assert controller.state.offers_retrust

    controller.begin_retrust()
    assert controller.state.pending_trust is not None
    controller.answer_trust(True)

    assert paths.authority.exists()
    assert AgentState.load(paths.state).agent_id == "a1"
    assert backend.restarts == 1
    assert controller.state.message == messages.TRUST_UPDATED.format(server=server.url)


def test_a_station_that_is_working_does_not_offer_to_trust_anything(backend, paths):
    AgentState(agent_id="a1", agent_key="k1", server_url="https://a.example").save(
        paths.state
    )
    StatusStore(paths.status).record_success()

    assert not WindowController(backend, _SyncExecutor()).state.offers_retrust


def test_the_window_is_busy_while_work_runs_and_ignores_a_second_click(backend, server):
    executor = _DeferredExecutor()
    controller = WindowController(backend, executor)
    controller.set_address(server.url)

    controller.check()
    controller.check()

    assert controller.state.busy
    assert not controller.state.can_connect
    assert len(executor.pending) == 1
    executor.finish()
    assert not controller.state.busy


def test_a_failure_nobody_expected_is_reported_in_russian_not_swallowed(
    backend, server, monkeypatch
):
    controller = WindowController(backend, _SyncExecutor())
    controller.set_address(server.url)

    def explode(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr("warden_agent.configurator.controller.probe", explode)
    controller.check()

    assert controller.state.message_is_error
    assert CYRILLIC.search(controller.state.message)
    assert not controller.state.busy


def test_listeners_hear_about_every_change(controller, server):
    heard = []
    controller.subscribe(lambda: heard.append(controller.state.message))

    controller.set_address(server.url)
    controller.check()

    assert heard and heard[-1] == messages.CHECK_UNTRUSTED
