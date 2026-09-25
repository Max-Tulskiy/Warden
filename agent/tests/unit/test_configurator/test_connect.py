"""Connecting a station: probing, trusting an authority, enrolling, saving.

Every test runs the whole flow against the shared TLS server, whose authority no
default context knows, and checks what lands in the agent's folder. Nothing is
stored unless the enrollment succeeded (R-10), and the token is never stored.
"""

import json

import pytest

from warden_agent.config import load_settings
from warden_agent.configurator.config_file import read_config, write_config
from warden_agent.configurator.logic import (
    Connected,
    RefusalReason,
    Refused,
    TrustNeeded,
    connect,
    fetch_authority,
    offer_from_reply,
)
from warden_agent.configurator.paths import AgentPaths
from warden_agent.core.transport import ServerClient, build_ssl_context
from warden_agent.state import AgentState

ONE_TIME_CODE = "s3cret-enrollment-token"


@pytest.fixture
def paths(tmp_path) -> AgentPaths:
    return AgentPaths.for_directory(tmp_path)


@pytest.fixture
def server(tls_server):
    """The test server, answering like a real one for the three routes involved."""

    def enroll(request):
        body = json.loads(request.body)
        if body["token"] == ONE_TIME_CODE:
            return 201, {"agent_id": "a1", "agent_key": "k1"}
        return 400, {"detail": "Invalid or expired enrollment token"}

    tls_server.answer("GET", "/health", body={"status": "ok"})
    tls_server.answer("GET", "/api/v1/agents/a1/tasks", body=[])
    tls_server.on("POST", "/api/v1/enroll", enroll)
    tls_server.answer("GET", "/api/v1/tls/ca", body={"pem": tls_server.authority_pem})
    return tls_server


def _files(paths: AgentPaths) -> list[str]:
    return sorted(item.name for item in paths.directory.iterdir())


def _paths_asked(server) -> list[str]:
    return [request.path for request in server.requests]


async def _confirmed(server, paths, **extra):
    offer = await fetch_authority(server.url)
    return await connect(
        paths, server_url=server.url, token=ONE_TIME_CODE, trust=offer, **extra
    )


async def test_an_untrusted_server_is_offered_for_trust_and_nothing_is_stored(
    server, paths
):
    outcome = await connect(paths, server_url=server.url, token=ONE_TIME_CODE)

    assert isinstance(outcome, TrustNeeded)
    assert outcome.offer.pem.strip() == server.authority_pem.strip()
    assert _files(paths) == ["configurator.log"]
    assert "/api/v1/enroll" not in _paths_asked(server)


async def test_a_confirmed_authority_enrolls_the_station_and_it_works_afterwards(
    server, paths
):
    outcome = await _confirmed(server, paths)

    assert outcome == Connected(server_url=server.url, agent_id="a1")
    assert paths.authority.read_text().strip() == server.authority_pem.strip()
    assert AgentState.load(paths.state) == AgentState(
        agent_id="a1", agent_key="k1", server_url=server.url
    )
    settings = load_settings(paths.config)
    assert settings.server_url == server.url
    assert settings.ca_file == paths.authority
    client = ServerClient(server.url, verify=build_ssl_context(settings.ca_file))
    assert await client.poll_tasks(agent_id="a1", agent_key="k1") == []
    await client.aclose()


async def test_only_the_agents_own_files_are_written(server, paths):
    await _confirmed(server, paths)

    assert _files(paths) == [
        "config.toml",
        "configurator.log",
        "server-ca.pem",
        "state.json",
    ]


async def test_a_matching_expected_fingerprint_connects_without_a_prompt(server, paths):
    offer = await fetch_authority(server.url)

    outcome = await connect(
        paths,
        server_url=server.url,
        token=ONE_TIME_CODE,
        expected_sha256=offer.fingerprint.lower(),  # colons and case are ignored
    )

    assert isinstance(outcome, Connected)
    assert paths.authority.exists()


async def test_a_different_expected_fingerprint_trusts_and_enrolls_nothing(
    server, paths
):
    outcome = await connect(
        paths, server_url=server.url, token=ONE_TIME_CODE, expected_sha256="ab" * 32
    )

    assert isinstance(outcome, Refused)
    assert outcome.reason is RefusalReason.FINGERPRINT_MISMATCH
    assert outcome.expected == "ab" * 32
    assert outcome.actual is not None and outcome.actual != outcome.expected
    assert _files(paths) == ["configurator.log"]
    assert "/api/v1/enroll" not in _paths_asked(server)


@pytest.mark.parametrize("nonsense", ["not a fingerprint", "ab" * 31, "zz" * 32])
async def test_an_expected_fingerprint_that_is_not_one_is_refused(
    server, paths, nonsense
):
    outcome = await connect(
        paths, server_url=server.url, token=ONE_TIME_CODE, expected_sha256=nonsense
    )

    assert isinstance(outcome, Refused)
    assert outcome.reason is RefusalReason.INVALID_FINGERPRINT
    assert _files(paths) == ["configurator.log"]


async def test_a_server_already_trusted_is_connected_without_any_trust_decision(
    server, paths
):
    write_config(paths.config, {"ca_file": paths.authority})
    paths.authority.write_text(server.authority_pem)

    outcome = await connect(paths, server_url=server.url, token=ONE_TIME_CODE)

    assert isinstance(outcome, Connected)
    assert "/api/v1/tls/ca" not in _paths_asked(server)
    assert paths.authority.read_text() == server.authority_pem


@pytest.mark.parametrize("token", ["unknown", "expired", "already-used"])
async def test_a_refused_token_stores_nothing_including_the_trust(server, paths, token):
    offer = await fetch_authority(server.url)

    outcome = await connect(paths, server_url=server.url, token=token, trust=offer)

    assert isinstance(outcome, Refused)
    assert outcome.reason is RefusalReason.TOKEN_REFUSED
    assert outcome.detail == "Invalid or expired enrollment token"
    assert _files(paths) == ["configurator.log"]


async def test_each_kind_of_failure_is_told_apart(server, paths, unreachable_url):
    unreachable = await connect(paths, server_url=unreachable_url, token=ONE_TIME_CODE)
    server.answer("GET", "/api/v1/tls/ca", 404, {"detail": "none"})
    no_authority = await connect(paths, server_url=server.url, token=ONE_TIME_CODE)
    refused_token = await connect(
        paths,
        server_url=server.url,
        token="wrong",
        trust=offer_from_reply({"pem": server.authority_pem}),
    )

    reasons = [outcome.reason for outcome in (unreachable, no_authority, refused_token)]
    assert reasons == [
        RefusalReason.UNREACHABLE,
        RefusalReason.NO_AUTHORITY,
        RefusalReason.TOKEN_REFUSED,
    ]


async def test_a_server_that_is_not_the_server_is_an_unexpected_reply(server, paths):
    server.answer("GET", "/health", 404, {"detail": "no"})
    write_config(paths.config, {"ca_file": paths.authority})
    paths.authority.write_text(server.authority_pem)

    outcome = await connect(paths, server_url=server.url, token=ONE_TIME_CODE)

    assert isinstance(outcome, Refused)
    assert outcome.reason is RefusalReason.UNEXPECTED_REPLY


@pytest.mark.parametrize(
    "address", ["", "not an address", "ftp://x.example", "https://"]
)
async def test_an_address_that_is_not_an_address_is_refused_before_any_request(
    server, paths, address
):
    outcome = await connect(paths, server_url=address, token=ONE_TIME_CODE)

    assert isinstance(outcome, Refused)
    assert outcome.reason is RefusalReason.INVALID_ADDRESS
    assert server.requests == []


async def test_a_station_already_enrolled_here_is_left_as_it_is(server, paths):
    await _confirmed(server, paths)
    before = {name: (paths.directory / name).read_bytes() for name in _files(paths)}
    server.requests.clear()

    outcome = await connect(paths, server_url=server.url, token=ONE_TIME_CODE)

    assert outcome == Connected(server_url=server.url, agent_id="a1", already=True)
    assert "/api/v1/enroll" not in _paths_asked(server)
    for name in ("config.toml", "server-ca.pem", "state.json"):
        assert (paths.directory / name).read_bytes() == before[name]


async def test_a_state_from_an_earlier_version_belongs_to_the_configured_server(
    server, paths
):
    write_config(paths.config, {"server_url": server.url})
    AgentState(agent_id="a1", agent_key="k1").save(paths.state)

    same = await connect(paths, server_url=server.url, token=ONE_TIME_CODE)
    other = await connect(
        paths, server_url="https://other.example", token=ONE_TIME_CODE
    )

    assert isinstance(same, Connected) and same.already
    assert isinstance(other, Refused)
    assert other.reason is RefusalReason.NEEDS_REPLACE


async def test_another_server_needs_a_confirmed_replacement(server, paths):
    AgentState(
        agent_id="old", agent_key="oldkey", server_url="https://old.example"
    ).save(paths.state)
    write_config(
        paths.config, {"server_url": "https://old.example", "ca_file": paths.authority}
    )
    paths.authority.write_text("the old server's authority")
    before = {name: (paths.directory / name).read_bytes() for name in _files(paths)}

    declined = await connect(paths, server_url=server.url, token=ONE_TIME_CODE)

    assert isinstance(declined, Refused)
    assert declined.reason is RefusalReason.NEEDS_REPLACE
    assert declined.current_server == "https://old.example"
    assert {n: (paths.directory / n).read_bytes() for n in before} == before

    offer = await fetch_authority(server.url)
    accepted = await connect(
        paths, server_url=server.url, token=ONE_TIME_CODE, trust=offer, replace=True
    )

    assert isinstance(accepted, Connected)
    assert AgentState.load(paths.state).agent_id == "a1"
    assert AgentState.load(paths.state).server_url == server.url
    assert paths.authority.read_text().strip() == server.authority_pem.strip()


async def test_trust_given_to_the_old_server_is_not_carried_to_the_new_one(
    server, paths
):
    """The old authority is not enough to reach the new server, and is dropped."""
    AgentState(
        agent_id="old", agent_key="oldkey", server_url="https://old.example"
    ).save(paths.state)
    write_config(
        paths.config, {"server_url": "https://old.example", "ca_file": paths.authority}
    )
    paths.authority.write_text(server.authority_pem)  # would verify the new server

    outcome = await connect(
        paths, server_url=server.url, token=ONE_TIME_CODE, replace=True
    )

    assert isinstance(outcome, TrustNeeded)


async def test_the_token_is_in_no_file_and_the_log_records_what_was_decided(
    server, paths
):
    offer = await fetch_authority(server.url)
    await connect(paths, server_url=server.url, token="wrong", trust=offer)
    await connect(paths, server_url=server.url, token=ONE_TIME_CODE, trust=offer)

    for name in _files(paths):
        text = (paths.directory / name).read_text()
        assert ONE_TIME_CODE not in text
        assert "wrong" not in text
    log = paths.log.read_text()
    assert offer.sha256 in log
    assert "trust accepted" in log
    assert "enrolled" in log
    assert server.url in log
    assert "refused" in log


async def test_the_token_does_not_reach_the_server_before_the_authority_is_trusted(
    server, paths
):
    offer = await fetch_authority(server.url)
    await connect(paths, server_url=server.url, token=ONE_TIME_CODE, trust=offer)

    before_enrollment = []
    for request in server.requests:
        if request.path == "/api/v1/enroll":
            break
        before_enrollment.append(request)
    assert before_enrollment  # the unverified fetch is in there
    for request in before_enrollment:
        assert ONE_TIME_CODE not in request.body.decode()
        assert ONE_TIME_CODE not in json.dumps(request.headers)
        assert "x-agent-key" not in request.headers


async def test_a_state_that_cannot_be_written_leaves_the_station_as_it_was(
    server, paths, monkeypatch
):
    def refuse(self, path):
        raise OSError("disk full")

    monkeypatch.setattr(AgentState, "save", refuse)
    offer = await fetch_authority(server.url)

    outcome = await connect(
        paths, server_url=server.url, token=ONE_TIME_CODE, trust=offer
    )

    assert isinstance(outcome, Refused)
    assert outcome.reason is RefusalReason.WRITE_FAILED
    assert not AgentState.load(paths.state).is_enrolled
    assert _files(paths) == ["configurator.log"]


async def test_a_configuration_that_cannot_be_rewritten_is_refused_before_enrolling(
    server, paths
):
    paths.config.write_text('server_url = "https://a.example"\n[table]\nkey = 1\n')
    offer = await fetch_authority(server.url)

    outcome = await connect(
        paths, server_url=server.url, token=ONE_TIME_CODE, trust=offer
    )

    assert isinstance(outcome, Refused)
    assert outcome.reason is RefusalReason.CONFIG_UNSUPPORTED
    assert "/api/v1/enroll" not in _paths_asked(server)  # the token was not spent


async def test_the_name_in_the_configuration_is_the_one_the_station_registers_under(
    server, paths
):
    write_config(paths.config, {"hostname": "FRONT-DESK-3"})
    seen = []

    def enroll(request):
        seen.append(json.loads(request.body)["hostname"])
        return 201, {"agent_id": "a1", "agent_key": "k1"}

    server.on("POST", "/api/v1/enroll", enroll)

    await _confirmed(server, paths)

    assert seen == ["FRONT-DESK-3"]
    assert read_config(paths.config)["hostname"] == "FRONT-DESK-3"


async def test_a_blank_token_is_refused_without_asking_the_server(server, paths):
    outcome = await connect(paths, server_url=server.url, token="   ")

    assert isinstance(outcome, Refused)
    assert outcome.reason is RefusalReason.TOKEN_MISSING
    assert server.requests == []


async def test_a_station_is_enrolled_where_the_configuration_says_the_agent_looks(
    server, paths, tmp_path
):
    elsewhere = tmp_path / "var" / "state.json"
    elsewhere.parent.mkdir()
    write_config(paths.config, {"state_path": elsewhere})

    outcome = await _confirmed(server, paths)

    assert isinstance(outcome, Connected)
    assert AgentState.load(elsewhere).is_enrolled
    assert not paths.state.exists()
    assert load_settings(paths.config).state_path == elsewhere
