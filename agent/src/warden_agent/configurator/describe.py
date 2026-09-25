"""Turns the outcome of a connection into the sentence a person reads."""

from collections.abc import Callable

from warden_agent.configurator import messages
from warden_agent.configurator.logic import (
    Connected,
    Outcome,
    ProbeKind,
    ProbeResult,
    RefusalReason,
    Refused,
    TrustNeeded,
)


def _refusal_texts(refused: Refused, server_url: str) -> dict[RefusalReason, str]:
    """Every reason's sentence; built lazily so only the reason at hand is filled in."""
    return {
        RefusalReason.INVALID_ADDRESS: messages.REFUSED_INVALID_ADDRESS,
        RefusalReason.INVALID_FINGERPRINT: messages.REFUSED_INVALID_FINGERPRINT,
        RefusalReason.TOKEN_MISSING: messages.REFUSED_BLANK_ENROLLMENT,
        RefusalReason.UNREACHABLE: messages.CHECK_UNREACHABLE.format(server=server_url),
        RefusalReason.UNEXPECTED_REPLY: messages.CHECK_UNEXPECTED.format(
            code=refused.detail
        ),
        RefusalReason.NO_AUTHORITY: messages.NO_AUTHORITY,
        RefusalReason.AUTHORITY_INVALID: messages.REFUSED_AUTHORITY_INVALID,
        RefusalReason.FINGERPRINT_MISMATCH: messages.FINGERPRINT_MISMATCH.format(
            expected=refused.expected, actual=refused.actual
        ),
        RefusalReason.CERTIFICATE_NOT_TRUSTED: messages.REFUSED_NOT_VERIFIED,
        RefusalReason.TOKEN_REFUSED: messages.ENROLLMENT_REFUSED.format(
            detail=refused.detail
        ),
        RefusalReason.SERVER_ERROR: messages.SERVER_FAILED.format(code=refused.detail),
        RefusalReason.NEEDS_REPLACE: messages.NEEDS_REPLACE.format(
            current=refused.current_server
        ),
        RefusalReason.CONFIG_UNSUPPORTED: messages.CONFIG_TOO_COMPLEX,
        RefusalReason.WRITE_FAILED: messages.REFUSED_WRITE_FAILED,
        RefusalReason.NOT_ENROLLED: messages.REFUSED_NOT_ENROLLED,
    }


def describe(outcome: Outcome, server_url: str) -> str:
    if isinstance(outcome, Connected):
        template = messages.ALREADY_CONNECTED if outcome.already else messages.CONNECTED
        return template.format(server=outcome.server_url)
    if isinstance(outcome, TrustNeeded):
        return messages.TRUST_OFFERED.format(
            subject=outcome.offer.subject, fingerprint=outcome.offer.fingerprint
        )
    return _refusal_texts(outcome, server_url)[outcome.reason]


def describe_probe(result: ProbeResult, server_url: str) -> str:
    texts: dict[ProbeKind, Callable[[], str]] = {
        ProbeKind.TRUSTED: lambda: messages.CHECK_TRUSTED,
        ProbeKind.NOT_TRUSTED: lambda: messages.CHECK_UNTRUSTED,
        ProbeKind.UNREACHABLE: lambda: messages.CHECK_UNREACHABLE.format(
            server=server_url
        ),
        ProbeKind.UNEXPECTED: lambda: messages.CHECK_UNEXPECTED.format(
            code=result.status_code
        ),
    }
    return texts[result.kind]()
