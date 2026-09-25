"""Trust in the server's certificate: which authorities the agent accepts.

These run real TLS handshakes against the shared `tls_server`, whose
certificate comes from an authority no default context knows.
"""

import httpx
import pytest

from warden_agent.core.transport import (
    EnrollmentError,
    FailureKind,
    ServerClient,
    build_ssl_context,
    classify_failure,
)
from warden_agent.errors import NotConfiguredError

ENROLLED = {"agent_id": "a1", "agent_key": "k1"}


async def _no_sleep(_seconds: float) -> None:
    return None


def _enroll(client: ServerClient):
    return client.enroll(token="tok", hostname="WS-01", os_name="linux")


async def test_an_authority_nobody_trusts_is_refused(tls_server):
    tls_server.answer("POST", "/api/v1/enroll", 201, ENROLLED)
    client = ServerClient(tls_server.url, verify=build_ssl_context(None))

    with pytest.raises(httpx.ConnectError) as refused:
        await _enroll(client)
    await client.aclose()

    assert classify_failure(refused.value) is FailureKind.CERTIFICATE_NOT_TRUSTED
    assert tls_server.requests == []


async def test_an_authority_named_in_the_configuration_is_accepted(
    tls_server, tmp_path
):
    tls_server.answer("POST", "/api/v1/enroll", 201, ENROLLED)
    ca_file = tmp_path / "server-ca.pem"
    ca_file.write_text(tls_server.authority_pem)
    client = ServerClient(tls_server.url, verify=build_ssl_context(ca_file))

    agent_id, agent_key = await _enroll(client)
    await client.aclose()

    assert (agent_id, agent_key) == ("a1", "k1")


@pytest.mark.parametrize("content", [None, "this is not a certificate\n", ""])
def test_an_authority_file_that_cannot_be_used_is_not_configured(tmp_path, content):
    ca_file = tmp_path / "server-ca.pem"
    if content is not None:
        ca_file.write_text(content)

    with pytest.raises(NotConfiguredError):
        build_ssl_context(ca_file)


async def test_a_client_given_no_context_keeps_the_default_behaviour(tls_server):
    client = ServerClient(tls_server.url)

    with pytest.raises(httpx.ConnectError):
        await _enroll(client)
    await client.aclose()


async def test_an_address_nothing_listens_on_is_unreachable(unreachable_url):
    client = ServerClient(unreachable_url, verify=build_ssl_context(None))

    with pytest.raises(httpx.ConnectError) as refused:
        await _enroll(client)
    await client.aclose()

    assert classify_failure(refused.value) is FailureKind.UNREACHABLE


async def test_a_refused_key_is_a_refused_credential(tls_server, tmp_path):
    tls_server.answer("GET", "/api/v1/agents/a1/tasks", 401, {"detail": "no"})
    ca_file = tmp_path / "ca.pem"
    ca_file.write_text(tls_server.authority_pem)
    client = ServerClient(
        tls_server.url, verify=build_ssl_context(ca_file), sleep=_no_sleep
    )

    with pytest.raises(httpx.HTTPStatusError) as refused:
        await client.poll_tasks(agent_id="a1", agent_key="wrong")
    await client.aclose()

    assert classify_failure(refused.value) is FailureKind.CREDENTIAL_REFUSED


async def test_a_failing_server_is_a_server_error(tls_server, tmp_path):
    tls_server.answer("GET", "/api/v1/agents/a1/tasks", 500, {"detail": "boom"})
    ca_file = tmp_path / "ca.pem"
    ca_file.write_text(tls_server.authority_pem)
    client = ServerClient(
        tls_server.url,
        verify=build_ssl_context(ca_file),
        sleep=_no_sleep,
        max_attempts=2,
    )

    with pytest.raises(httpx.HTTPStatusError) as failed:
        await client.poll_tasks(agent_id="a1", agent_key="k1")
    await client.aclose()

    assert classify_failure(failed.value) is FailureKind.SERVER_ERROR


@pytest.mark.parametrize(
    ("failure", "kind"),
    [
        (EnrollmentError("the token was used"), FailureKind.CREDENTIAL_REFUSED),
        (httpx.ReadTimeout("slow"), FailureKind.UNREACHABLE),
        (ValueError("anything else"), FailureKind.OTHER),
    ],
)
def test_other_failures_are_sorted_into_the_remaining_kinds(failure, kind):
    assert classify_failure(failure) is kind


def test_the_kinds_are_the_codes_the_status_file_stores():
    assert {kind.value for kind in FailureKind} == {
        "unreachable",
        "certificate_not_trusted",
        "credential_refused",
        "server_error",
        "other",
    }
