"""The one place that decides the operating policy (constitution D-11).

The server's configuration gives the three editable values their defaults, and
a policy an administrator saved outranks it until it is returned to the
defaults. Every use of the window limit, the enrollment token lifetime, and the
session lifetime reads it from here, and nothing else reads those settings, so
there is exactly one answer to "which value is in force".
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from warden_server.config import get_settings
from warden_server.models.policy import PolicyOverride
from warden_server.schemas.policy import WINDOW_HOURS_CEILING, PolicyValues

_ROW_ID = 1
_FIELDS = (
    "max_request_window_hours",
    "enrollment_token_ttl_hours",
    "session_lifetime_minutes",
)


@dataclass(frozen=True)
class EffectivePolicy:
    """What is in force now, and whether an administrator saved it."""

    max_request_window_hours: int
    enrollment_token_ttl_hours: int
    session_lifetime_minutes: int
    overridden: bool


def _clamped(values: PolicyValues) -> PolicyValues:
    """The request window is never above the constitution's four hours."""
    return values.model_copy(
        update={
            "max_request_window_hours": min(
                values.max_request_window_hours, WINDOW_HOURS_CEILING
            )
        }
    )


def configured_defaults() -> PolicyValues:
    """What the server's configuration says, with the window held to the ceiling."""
    settings = get_settings()
    return _clamped(
        PolicyValues(
            max_request_window_hours=settings.max_request_window_hours,
            enrollment_token_ttl_hours=settings.enrollment_token_ttl_hours,
            session_lifetime_minutes=settings.jwt_expire_minutes,
        )
    )


def _values_of(row: PolicyOverride) -> PolicyValues:
    return PolicyValues(**{field: getattr(row, field) for field in _FIELDS})


def effective_policy(db: Session) -> EffectivePolicy:
    """The saved policy if there is one, else the configured defaults.

    Read afresh on every call, with no cache, so a change applies from the next
    use and is right across several server processes.
    """
    row = db.get(PolicyOverride, _ROW_ID)
    values = _clamped(_values_of(row)) if row is not None else configured_defaults()
    return EffectivePolicy(**values.model_dump(), overridden=row is not None)


def _diff(before: PolicyValues, after: PolicyValues) -> dict[str, list[Any]]:
    return {
        field: [getattr(before, field), getattr(after, field)]
        for field in _FIELDS
        if getattr(before, field) != getattr(after, field)
    }


def _update(
    row: PolicyOverride, values: PolicyValues, actor: str, now: datetime
) -> dict[str, list[Any]]:
    changes = _diff(_values_of(row), values)
    if changes:
        for field in _FIELDS:
            setattr(row, field, getattr(values, field))
        row.updated_at = now
        row.updated_by = actor
    return changes


def save_policy(
    db: Session, values: PolicyValues, *, actor: str
) -> dict[str, list[Any]]:
    """Save all three values and return what changed, as `{name: [old, new]}`.

    The first save also reports `overridden` going from false to true, even when
    no value moves, because it changes who decides. Saving what is already in
    force returns an empty dict. The caller commits and audits.

    Call it before other writes in the request: if two administrators save for
    the first time at once, the loser's insert fails, the transaction is rolled
    back, and the save is redone as an update of the winner's row.
    """
    now = datetime.now(UTC)
    row = db.get(PolicyOverride, _ROW_ID)
    if row is not None:
        return _update(row, values, actor, now)

    before = configured_defaults()
    db.add(
        PolicyOverride(
            id=_ROW_ID, **values.model_dump(), updated_at=now, updated_by=actor
        )
    )
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        winner = db.get(PolicyOverride, _ROW_ID)
        if winner is None:
            raise
        return _update(winner, values, actor, now)
    return {**_diff(before, values), "overridden": [False, True]}


def reset_policy(db: Session) -> dict[str, list[Any]]:
    """Forget the saved policy, so the configured defaults apply again.

    Returns the values that go back, as `{name: [saved, default]}`, plus
    `overridden` going from true to false; an empty dict when nothing was
    saved. The caller commits and audits.
    """
    row = db.get(PolicyOverride, _ROW_ID)
    if row is None:
        return {}
    changes = _diff(_values_of(row), configured_defaults())
    db.delete(row)
    return {**changes, "overridden": [True, False]}
