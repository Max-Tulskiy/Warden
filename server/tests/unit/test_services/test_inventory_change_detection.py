"""Tests for the configuration-change detector (constitution principle 6)."""

import uuid

from warden_server.models.inventory import InventorySnapshot
from warden_server.services.inventory import ingest_snapshot


def test_first_snapshot_for_a_station_is_recorded_as_a_baseline_change(db_session):
    agent_id = uuid.uuid4()

    change = ingest_snapshot(
        db_session,
        agent_id=agent_id,
        hardware={"cpu": "x86_64"},
        software={"nginx": "1.24"},
    )

    assert change is not None
    expected_added = {"hardware": {"cpu": "x86_64"}, "software": {"nginx": "1.24"}}
    assert change.added == expected_added
    assert change.removed == {"hardware": {}, "software": {}}


def test_an_identical_snapshot_produces_no_change(db_session):
    agent_id = uuid.uuid4()
    ingest_snapshot(
        db_session, agent_id=agent_id, hardware={"cpu": "x86_64"}, software={}
    )
    db_session.commit()

    change = ingest_snapshot(
        db_session, agent_id=agent_id, hardware={"cpu": "x86_64"}, software={}
    )

    assert change is None


def test_a_changed_snapshot_produces_a_change_with_the_right_diff(db_session):
    agent_id = uuid.uuid4()
    ingest_snapshot(
        db_session,
        agent_id=agent_id,
        hardware={"cpu": "x86_64"},
        software={"nginx": "1.24", "curl": "8.0"},
    )
    db_session.commit()

    change = ingest_snapshot(
        db_session,
        agent_id=agent_id,
        hardware={"cpu": "arm64"},
        software={"nginx": "1.26", "git": "2.44"},
    )

    assert change is not None
    assert change.modified["hardware"] == {"cpu": {"old": "x86_64", "new": "arm64"}}
    assert change.modified["software"] == {"nginx": {"old": "1.24", "new": "1.26"}}
    assert change.added["software"] == {"git": "2.44"}
    assert change.removed["software"] == {"curl": "8.0"}


def test_every_snapshot_is_kept_even_when_unchanged(db_session):
    agent_id = uuid.uuid4()
    ingest_snapshot(db_session, agent_id=agent_id, hardware={}, software={})
    db_session.commit()
    ingest_snapshot(db_session, agent_id=agent_id, hardware={}, software={})
    db_session.commit()

    snapshots = (
        db_session.query(InventorySnapshot)
        .filter(InventorySnapshot.agent_id == agent_id)
        .all()
    )
    assert len(snapshots) == 2


def test_a_returned_change_already_has_its_id(db_session):
    """Callers such as the audit entry refer to the change by id, and an id
    the database has not assigned yet reads as None."""
    change = ingest_snapshot(
        db_session,
        agent_id=uuid.uuid4(),
        hardware={"cpu": "x86_64"},
        software={"nginx": "1.24"},
    )

    assert change is not None
    assert isinstance(change.id, uuid.UUID)
