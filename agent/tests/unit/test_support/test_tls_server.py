"""The shared TLS server behaves like a server whose authority is unknown."""

import ssl

import httpx
import pytest


def test_a_default_context_refuses_the_test_server(tls_server):
    tls_server.answer("GET", "/health", body={"status": "ok"})

    with pytest.raises(httpx.ConnectError):
        httpx.get(f"{tls_server.url}/health", verify=ssl.create_default_context())


def test_a_context_that_trusts_its_authority_is_answered(tls_server):
    tls_server.answer("GET", "/health", body={"status": "ok"})
    context = ssl.create_default_context(cadata=tls_server.authority_pem)

    response = httpx.get(f"{tls_server.url}/health", verify=context)

    assert response.json() == {"status": "ok"}
    assert [request.path for request in tls_server.requests] == ["/health"]


def test_a_rotated_authority_is_no_longer_trusted_by_the_old_one(tls_server):
    tls_server.answer("GET", "/health", body={"status": "ok"})
    old_context = ssl.create_default_context(cadata=tls_server.authority_pem)

    tls_server.rotate_authority()

    with pytest.raises(httpx.ConnectError):
        httpx.get(f"{tls_server.url}/health", verify=old_context)


def test_nothing_answers_on_the_unreachable_address(unreachable_url):
    with pytest.raises(httpx.ConnectError):
        httpx.get(f"{unreachable_url}/health")
