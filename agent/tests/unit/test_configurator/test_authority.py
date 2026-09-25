"""Probing an address and fetching the server's authority, over real TLS."""

from datetime import UTC, datetime

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes

from warden_agent.configurator.logic import (
    InvalidAuthorityError,
    NoAuthorityError,
    ProbeKind,
    fetch_authority,
    probe,
)


def _independent_fingerprint(pem: str) -> str:
    """The SHA-256 of a certificate, by a different library than the code under test."""
    certificate = x509.load_pem_x509_certificate(pem.encode("ascii"))
    return certificate.fingerprint(hashes.SHA256()).hex()


async def test_a_trusted_server_is_reported_reachable_and_trusted(tls_server):
    tls_server.answer("GET", "/health", body={"status": "ok"})

    result = await probe(tls_server.url, extra_ca_pem=tls_server.authority_pem)

    assert result.kind is ProbeKind.TRUSTED


async def test_a_configured_authority_file_counts_as_trusted(tls_server, tmp_path):
    tls_server.answer("GET", "/health", body={"status": "ok"})
    ca_file = tmp_path / "server-ca.pem"
    ca_file.write_text(tls_server.authority_pem)

    assert (await probe(tls_server.url, ca_file=ca_file)).kind is ProbeKind.TRUSTED


async def test_a_server_with_an_unknown_authority_is_reported_not_trusted(tls_server):
    tls_server.answer("GET", "/health", body={"status": "ok"})

    result = await probe(tls_server.url)

    assert result.kind is ProbeKind.NOT_TRUSTED
    assert tls_server.requests == []


async def test_an_address_nothing_listens_on_is_reported_unreachable(unreachable_url):
    assert (await probe(unreachable_url)).kind is ProbeKind.UNREACHABLE


@pytest.mark.parametrize(
    ("status", "body"),
    [(404, {"detail": "no"}), (200, {"hello": "world"}), (200, None)],
)
async def test_an_address_that_is_not_the_server_is_an_unexpected_reply(
    tls_server, status, body
):
    tls_server.answer("GET", "/health", status, body)

    result = await probe(tls_server.url, extra_ca_pem=tls_server.authority_pem)

    assert result.kind is ProbeKind.UNEXPECTED
    assert result.status_code == status


async def test_the_offer_is_computed_here_and_the_servers_own_fingerprint_is_ignored(
    tls_server,
):
    tls_server.answer(
        "GET",
        "/api/v1/tls/ca",
        body={"pem": tls_server.authority_pem, "sha256": "0" * 64},
    )

    offer = await fetch_authority(tls_server.url)

    assert offer.sha256 == _independent_fingerprint(tls_server.authority_pem)
    assert offer.pem.strip() == tls_server.authority_pem.strip()


async def test_the_offer_shows_who_issued_it_and_until_when(tls_server):
    tls_server.answer("GET", "/api/v1/tls/ca", body={"pem": tls_server.authority_pem})

    offer = await fetch_authority(tls_server.url)

    assert "trustme" in offer.subject  # the test authority names only O and OU
    assert offer.not_after > datetime.now(UTC)
    assert offer.not_before < datetime.now(UTC)


async def test_the_fingerprint_is_shown_in_pairs_for_people_to_compare(tls_server):
    tls_server.answer("GET", "/api/v1/tls/ca", body={"pem": tls_server.authority_pem})

    offer = await fetch_authority(tls_server.url)

    shown = offer.fingerprint
    assert shown == shown.upper()
    assert shown.replace(":", "").lower() == offer.sha256
    assert len(shown) == 95


async def test_the_fetch_carries_nothing_but_the_request_itself(tls_server):
    tls_server.answer("GET", "/api/v1/tls/ca", body={"pem": tls_server.authority_pem})

    await fetch_authority(tls_server.url)

    (request,) = tls_server.requests
    assert request.body == b""
    assert "authorization" not in request.headers
    assert "x-agent-key" not in request.headers


async def test_a_server_with_no_authority_of_its_own_says_so(tls_server):
    tls_server.answer("GET", "/api/v1/tls/ca", 404, {"detail": "none"})

    with pytest.raises(NoAuthorityError):
        await fetch_authority(tls_server.url)


@pytest.mark.parametrize(
    "body",
    [
        {"pem": "this is not a certificate"},
        {"pem": ""},
        {"nothing": "here"},
        ["a", "list"],
    ],
)
async def test_an_offer_that_is_not_a_certificate_is_refused(tls_server, body):
    tls_server.answer("GET", "/api/v1/tls/ca", body=body)

    with pytest.raises(InvalidAuthorityError):
        await fetch_authority(tls_server.url)


async def test_only_the_first_certificate_of_an_offer_is_kept(tls_server):
    first = tls_server.authority_pem
    tls_server.rotate_authority()
    second = tls_server.authority_pem
    tls_server.answer("GET", "/api/v1/tls/ca", body={"pem": first + second})

    offer = await fetch_authority(tls_server.url)

    assert offer.pem.count("BEGIN CERTIFICATE") == 1
    assert offer.sha256 == _independent_fingerprint(first)
