"""Tests for the one place that decides the operating policy (spec 006)."""

import pytest
from sqlalchemy.exc import IntegrityError

from warden_server.config import Settings
from warden_server.schemas.policy import (
    SESSION_MINUTES_BOUNDS,
    TOKEN_TTL_HOURS_BOUNDS,
    WINDOW_HOURS_BOUNDS,
    WINDOW_HOURS_CEILING,
    PolicyValues,
)
from warden_server.services import policy as policy_service


def _configure(monkeypatch, **overrides):
    """Make the server's configuration say something, without touching the env."""
    settings = Settings(**overrides)
    monkeypatch.setattr(policy_service, "get_settings", lambda: settings)
    return settings


def _values(window=2, token=12, session=60) -> PolicyValues:
    return PolicyValues(
        max_request_window_hours=window,
        enrollment_token_ttl_hours=token,
        session_lifetime_minutes=session,
    )


def test_the_bounds_and_the_ceiling_are_the_ones_the_constitution_and_plan_fix():
    assert WINDOW_HOURS_CEILING == 4
    assert WINDOW_HOURS_BOUNDS == (1, 4)
    assert TOKEN_TTL_HOURS_BOUNDS == (1, 168)
    assert SESSION_MINUTES_BOUNDS == (5, 1440)


def test_the_configured_defaults_are_what_the_settings_say(monkeypatch):
    _configure(
        monkeypatch,
        max_request_window_hours=3,
        enrollment_token_ttl_hours=12,
        jwt_expire_minutes=90,
    )

    assert policy_service.configured_defaults() == _values(3, 12, 90)


def test_a_configured_window_above_the_ceiling_is_clamped_to_it(monkeypatch):
    _configure(monkeypatch, max_request_window_hours=6)

    assert policy_service.configured_defaults().max_request_window_hours == 4


def test_with_nothing_saved_the_effective_policy_is_the_defaults(
    db_session, monkeypatch
):
    _configure(monkeypatch)

    effective = policy_service.effective_policy(db_session)

    assert effective.overridden is False
    assert (
        effective.max_request_window_hours,
        effective.enrollment_token_ttl_hours,
        effective.session_lifetime_minutes,
    ) == (4, 24, 480)


def test_a_configured_window_of_six_never_takes_effect(db_session, monkeypatch):
    """Principle 3: the ceiling holds with nothing saved and a configuration
    that says otherwise."""
    _configure(monkeypatch, max_request_window_hours=6)

    assert policy_service.effective_policy(db_session).max_request_window_hours == 4


def test_a_saved_policy_is_what_is_in_force(db_session, monkeypatch):
    _configure(monkeypatch)
    policy_service.save_policy(db_session, _values(2, 12, 60), actor="admin")
    db_session.commit()

    effective = policy_service.effective_policy(db_session)

    assert effective.overridden is True
    assert (
        effective.max_request_window_hours,
        effective.enrollment_token_ttl_hours,
        effective.session_lifetime_minutes,
    ) == (2, 12, 60)


def test_a_saved_policy_survives_a_change_of_the_configuration(db_session, monkeypatch):
    _configure(monkeypatch)
    policy_service.save_policy(db_session, _values(2, 12, 60), actor="admin")
    db_session.commit()

    _configure(monkeypatch, max_request_window_hours=1, jwt_expire_minutes=15)

    assert policy_service.effective_policy(db_session).session_lifetime_minutes == 60


def test_the_first_save_reports_every_value_and_the_new_override(
    db_session, monkeypatch
):
    _configure(monkeypatch)

    changes = policy_service.save_policy(db_session, _values(2, 12, 60), actor="admin")

    assert changes == {
        "max_request_window_hours": [4, 2],
        "enrollment_token_ttl_hours": [24, 12],
        "session_lifetime_minutes": [480, 60],
        "overridden": [False, True],
    }


def test_a_first_save_equal_to_the_defaults_still_reports_the_override(
    db_session, monkeypatch
):
    """It changes who decides, even though no value moves."""
    _configure(monkeypatch)

    changes = policy_service.save_policy(db_session, _values(4, 24, 480), actor="admin")

    assert changes == {"overridden": [False, True]}


def test_a_later_save_reports_only_the_value_that_changed(db_session, monkeypatch):
    _configure(monkeypatch)
    policy_service.save_policy(db_session, _values(2, 12, 60), actor="admin")
    db_session.commit()

    changes = policy_service.save_policy(db_session, _values(3, 12, 60), actor="admin")

    assert changes == {"max_request_window_hours": [2, 3]}


def test_an_identical_save_reports_nothing(db_session, monkeypatch):
    _configure(monkeypatch)
    policy_service.save_policy(db_session, _values(2, 12, 60), actor="admin")
    db_session.commit()

    assert (
        policy_service.save_policy(db_session, _values(2, 12, 60), actor="admin") == {}
    )


def test_a_save_records_who_made_it(db_session, monkeypatch):
    _configure(monkeypatch)

    policy_service.save_policy(db_session, _values(), actor="ivanova")
    db_session.commit()

    row = db_session.get(policy_service.PolicyOverride, 1)
    assert row is not None and row.updated_by == "ivanova"


def test_a_reset_returns_to_the_defaults_and_reports_what_moved(
    db_session, monkeypatch
):
    _configure(monkeypatch)
    policy_service.save_policy(db_session, _values(2, 24, 60), actor="admin")
    db_session.commit()

    changes = policy_service.reset_policy(db_session)
    db_session.commit()

    assert changes == {
        "max_request_window_hours": [2, 4],
        "session_lifetime_minutes": [60, 480],
        "overridden": [True, False],
    }
    assert policy_service.effective_policy(db_session).overridden is False


def test_a_reset_with_nothing_saved_reports_nothing(db_session, monkeypatch):
    _configure(monkeypatch)

    assert policy_service.reset_policy(db_session) == {}


def test_a_first_save_that_loses_a_race_retries_and_updates(db_session, monkeypatch):
    """Two administrators saving for the first time at once: the row exists by the
    time the second one inserts, so its insert fails and it must update instead."""
    _configure(monkeypatch)
    policy_service.save_policy(db_session, _values(2, 12, 60), actor="first")
    db_session.commit()

    db_session.expunge_all()  # a second process would not share this session
    real_get = db_session.get
    lookups = []

    def blind_the_first_time(model, ident, **kwargs):
        lookups.append(ident)
        return None if len(lookups) == 1 else real_get(model, ident, **kwargs)

    monkeypatch.setattr(db_session, "get", blind_the_first_time)

    changes = policy_service.save_policy(db_session, _values(3, 12, 60), actor="second")
    db_session.commit()

    assert changes == {"max_request_window_hours": [2, 3]}
    assert policy_service.effective_policy(db_session).max_request_window_hours == 3


def test_a_failure_that_is_not_the_race_is_not_swallowed(db_session, monkeypatch):
    _configure(monkeypatch)
    monkeypatch.setattr(db_session, "get", lambda *args, **kwargs: None)

    def always_conflicts():
        raise IntegrityError("INSERT", {}, Exception("still failing"))

    monkeypatch.setattr(db_session, "flush", always_conflicts)

    with pytest.raises(Exception, match="still failing"):
        policy_service.save_policy(db_session, _values(), actor="admin")
