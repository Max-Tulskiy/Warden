"""Trusting a new authority for a station that is already enrolled (A-15)."""

import json

import httpx
import pytest

from warden_agent.config import load_settings
from warden_agent.configurator.backend import ServiceState
from warden_agent.configurator.logic import (
    Connected,
    RefusalReason,
    Refused,
    TrustNeeded,
    begin_retrust,
    connect,
    fetch_authority,
    read_status,
    retrust,
)
from warden_agent.configurator.paths import AgentPaths
from warden_agent.core.transport import ServerClient, build_ssl_context
from warden_agent.state import AgentState
from warden_agent.status import StatusStore

CODE = "s3cret-enrollment-token"


@pytest.fixture
def paths(tmp_path) -> AgentPaths:
    return AgentPaths.for_directory(tmp_path)


@pytest.fixture
def enrolled(tls_server, paths):
    """A station enrolled through the window, against the test server."""
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

    async def enroll():
        offer = await fetch_authority(tls_server.url)
        return await connect(paths, server_url=tls_server.url, token=CODE, trust=offer)

    return enroll


async def _no_sleep(_seconds: float) -> None:
    return None


def _client(server, paths: AgentPaths) -> ServerClient:
    """A client the way the service builds it from the saved configuration."""
    return ServerClient(
        server.url,
        verify=build_ssl_context(load_settings(paths.config).ca_file),
        sleep=_no_sleep,
        max_attempts=1,
    )


def _snapshot(paths: AgentPaths) -> dict[str, bytes]:
    return {
        item.name: item.read_bytes()
        for item in paths.directory.iterdir()
        if item.name != "configurator.log"
    }


async def test_a_rebuilt_server_is_trusted_again_without_enrolling_again(
    tls_server, paths, enrolled
):
    await enrolled()
    old_state = AgentState.load(paths.state)
    tls_server.rotate_authority()
    client = _client(tls_server, paths)
    with pytest.raises(httpx.ConnectError):
        await client.poll_tasks(agent_id="a1", agent_key="k1")
    await client.aclose()

    begun = await begin_retrust(paths)
    assert isinstance(begun, TrustNeeded)
    outcome = await retrust(paths, offer=begun.offer)

    assert isinstance(outcome, Connected) and outcome.already
    assert AgentState.load(paths.state) == old_state
    assert paths.authority.read_text().strip() == tls_server.authority_pem.strip()
    client = _client(tls_server, paths)
    assert await client.poll_tasks(agent_id="a1", agent_key="k1") == []
    await client.aclose()
    enrollments = [r for r in tls_server.requests if r.path == "/api/v1/enroll"]
    assert len(enrollments) == 1  # only the original one


async def test_a_different_expected_fingerprint_changes_nothing(
    tls_server, paths, enrolled
):
    await enrolled()
    tls_server.rotate_authority()
    begun = await begin_retrust(paths)
    before = _snapshot(paths)

    outcome = await retrust(paths, offer=begun.offer, expected_sha256="cd" * 32)

    assert isinstance(outcome, Refused)
    assert outcome.reason is RefusalReason.FINGERPRINT_MISMATCH
    assert _snapshot(paths) == before


async def test_an_offer_that_does_not_verify_the_server_changes_nothing(
    tls_server, paths, enrolled
):
    await enrolled()
    stale = await fetch_authority(tls_server.url)
    tls_server.rotate_authority()
    before = _snapshot(paths)

    outcome = await retrust(paths, offer=stale)

    assert isinstance(outcome, Refused)
    assert outcome.reason is RefusalReason.CERTIFICATE_NOT_TRUSTED
    assert _snapshot(paths) == before


async def test_a_station_that_is_not_enrolled_has_nothing_to_trust_again(
    tls_server, paths
):
    tls_server.answer("GET", "/api/v1/tls/ca", body={"pem": tls_server.authority_pem})
    offer = await fetch_authority(tls_server.url)

    outcome = await retrust(paths, offer=offer)
    begun = await begin_retrust(paths)

    assert outcome == Refused(RefusalReason.NOT_ENROLLED)
    assert begun == Refused(RefusalReason.NOT_ENROLLED)


async def test_a_server_with_no_authority_of_its_own_offers_nothing_to_trust(
    tls_server, paths, enrolled
):
    await enrolled()
    tls_server.answer("GET", "/api/v1/tls/ca", 404, {"detail": "none"})

    begun = await begin_retrust(paths)

    assert begun == Refused(RefusalReason.NO_AUTHORITY)


def test_an_empty_folder_reads_as_a_station_with_nothing_set(paths):
    status = read_status(paths, ServiceState.NOT_INSTALLED)

    assert status.service is ServiceState.NOT_INSTALLED
    assert not status.enrolled
    assert status.enrolled_server is None
    assert status.configured_server is None
    assert not status.trusts_authority
    assert status.agent.state is None


async def test_an_enrolled_station_reports_its_server_trust_and_agent_status(
    tls_server, paths, enrolled
):
    await enrolled()
    StatusStore(paths.status).record_success()

    status = read_status(paths, ServiceState.RUNNING)

    assert status.service is ServiceState.RUNNING
    assert status.enrolled
    assert status.enrolled_server == tls_server.url
    assert status.configured_server == tls_server.url
    assert status.trusts_authority
    assert status.agent.last_success_at is not None


def test_a_state_from_an_earlier_version_shows_the_configured_server(paths):
    paths.config.write_text('server_url = "https://a.example"\n')
    AgentState(agent_id="a1", agent_key="k1").save(paths.state)

    status = read_status(paths, ServiceState.STOPPED)

    assert status.enrolled
    assert status.enrolled_server == "https://a.example"


def test_a_configured_but_not_enrolled_station_offers_its_address_to_fill_in(paths):
    paths.config.write_text('server_url = "https://a.example"\n')

    status = read_status(paths, ServiceState.RUNNING)

    assert not status.enrolled
    assert status.configured_server == "https://a.example"
