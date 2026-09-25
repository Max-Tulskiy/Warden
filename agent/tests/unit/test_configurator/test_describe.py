"""Every way a connection can end has a Russian sentence."""

import re

import pytest

from warden_agent.configurator.describe import describe
from warden_agent.configurator.logic import (
    Connected,
    RefusalReason,
    Refused,
    TrustNeeded,
    offer_from_reply,
)

CYRILLIC = re.compile("[А-Яа-яЁё]")
SERVER = "https://warden.example.internal"


@pytest.mark.parametrize("reason", list(RefusalReason))
def test_every_refusal_reason_is_explained_in_russian(reason):
    refused = Refused(
        reason,
        detail="подробность",
        expected="ab" * 32,
        actual="cd" * 32,
        current_server="https://old.example",
    )

    text = describe(refused, SERVER)

    assert CYRILLIC.search(text)
    assert "{" not in text


def test_a_connected_station_and_an_already_connected_one_are_told_apart():
    fresh = describe(Connected(SERVER, "a1"), SERVER)
    already = describe(Connected(SERVER, "a1", already=True), SERVER)

    assert fresh != already
    assert SERVER in fresh and SERVER in already


def test_a_trust_offer_shows_who_issued_it_and_the_fingerprint(tls_server):
    offer = offer_from_reply({"pem": tls_server.authority_pem})

    text = describe(TrustNeeded(offer), SERVER)

    assert offer.fingerprint in text
    assert offer.subject in text
    assert CYRILLIC.search(text)


def test_a_mismatch_names_both_fingerprints():
    text = describe(
        Refused(
            RefusalReason.FINGERPRINT_MISMATCH, expected="ab" * 32, actual="cd" * 32
        ),
        SERVER,
    )

    assert "ab" * 32 in text and "cd" * 32 in text
