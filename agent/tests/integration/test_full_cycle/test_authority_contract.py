"""The server's published authority, read by the agent's own parser.

The two sides of `GET /api/v1/tls/ca` are exercised together: the real server
app answers, and the agent's `offer_from_reply` turns that answer into what the
window shows, so neither can drift from the contract on its own (principle 11).
"""

import hashlib
import ssl
from pathlib import Path

from warden_server.api import tls as server_tls
from warden_server.config import Settings

from warden_agent.configurator.logic import offer_from_reply

AUTHORITY = (
    Path(__file__).parents[4]
    / "server"
    / "tests"
    / "integration"
    / "test_tls_authority"
    / "authority.pem"
)


async def test_the_agent_reads_what_the_real_server_publishes(raw_client, monkeypatch):
    settings = Settings(tls_ca_path=AUTHORITY)
    monkeypatch.setattr(server_tls, "get_settings", lambda: settings)

    reply = await raw_client.get("/api/v1/tls/ca")
    offer = offer_from_reply(reply.json())

    assert reply.status_code == 200
    der = ssl.PEM_cert_to_DER_cert(AUTHORITY.read_text())
    assert offer.sha256 == hashlib.sha256(der).hexdigest()
    assert offer.sha256 == reply.json()["sha256"]
    assert "Warden Test Local Authority" in offer.subject
