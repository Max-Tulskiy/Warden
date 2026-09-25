"""Integration: the server publishes its own certificate authority (spec 009, R-5).

`authority.pem` is a throwaway certificate made for these tests with
`openssl req -x509`; `FINGERPRINT` is what `openssl x509 -fingerprint -sha256`
printed for it, so the value the endpoint computes is compared with one that
came from a different tool.
"""

from pathlib import Path

import pytest

from warden_server.api import tls as tls_api
from warden_server.config import Settings

AUTHORITY = Path(__file__).with_name("authority.pem")
FINGERPRINT = "b171395da10849824071f08074ebc29945c7dd3e3187480647ea0a60cc130833"

# Not a key: text shaped like the block of one, to see that nothing but a
# certificate is ever returned from a file that also carries such a block.
KEY_BLOCK = (
    "-----BEGIN PRIVATE KEY-----\n"
    "bm90IGEgcmVhbCBrZXksIGp1c3QgdGhlIHNoYXBlIG9mIG9uZQ==\n"
    "-----END PRIVATE KEY-----\n"
)


@pytest.fixture
def publish(monkeypatch):
    """Point the endpoint at a file (or at none), the way the setting would."""

    def _publish(path: Path | None) -> None:
        settings = Settings(tls_ca_path=path)
        monkeypatch.setattr(tls_api, "get_settings", lambda: settings)

    return _publish


def test_the_authority_is_served_without_any_credential(client, publish):
    publish(AUTHORITY)

    response = client.get("/api/v1/tls/ca")

    assert response.status_code == 200
    assert response.json()["pem"].strip() == AUTHORITY.read_text().strip()


def test_the_fingerprint_is_the_sha256_of_the_certificate(client, publish):
    publish(AUTHORITY)

    body = client.get("/api/v1/tls/ca").json()

    assert body["sha256"] == FINGERPRINT
    assert len(body["sha256"]) == 64
    assert body["sha256"] == body["sha256"].lower()


def test_a_file_that_also_holds_a_private_key_returns_only_the_certificate(
    client, publish, tmp_path
):
    mixed = tmp_path / "mixed.pem"
    mixed.write_text(KEY_BLOCK + AUTHORITY.read_text() + KEY_BLOCK)
    publish(mixed)

    response = client.get("/api/v1/tls/ca")

    assert response.status_code == 200
    assert "PRIVATE KEY" not in response.text
    assert response.json()["sha256"] == FINGERPRINT


def test_only_the_first_certificate_of_a_chain_is_returned(client, publish, tmp_path):
    chain = tmp_path / "chain.pem"
    chain.write_text(AUTHORITY.read_text() * 2)
    publish(chain)

    body = client.get("/api/v1/tls/ca").json()

    assert body["pem"].count("BEGIN CERTIFICATE") == 1


def test_no_configured_path_means_the_server_has_no_authority(client, publish):
    publish(None)

    assert client.get("/api/v1/tls/ca").status_code == 404


def test_a_missing_file_means_the_server_has_no_authority(client, publish, tmp_path):
    publish(tmp_path / "absent.pem")

    assert client.get("/api/v1/tls/ca").status_code == 404


def test_a_file_without_a_certificate_means_the_server_has_no_authority(
    client, publish, tmp_path
):
    only_a_key = tmp_path / "key.pem"
    only_a_key.write_text(KEY_BLOCK)
    publish(only_a_key)

    response = client.get("/api/v1/tls/ca")

    assert response.status_code == 404
    assert "PRIVATE KEY" not in response.text


def test_the_file_is_read_at_request_time(client, publish, tmp_path):
    """The proxy creates its authority after the server may already be up."""
    late = tmp_path / "late.pem"
    publish(late)
    assert client.get("/api/v1/tls/ca").status_code == 404

    late.write_text(AUTHORITY.read_text())

    assert client.get("/api/v1/tls/ca").status_code == 200
