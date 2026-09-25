"""Tests for `complete_task` dropping events already known for a station.

Covers `specs/007-event-deduplication/spec.md` R-1, R-2, R-4 and acceptance
criteria A-1..A-5: overlapping window requests deliver the same underlying
occurrence more than once, and the server must store it only once, without
ever merging two genuinely different occurrences.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select

from warden_server.models.event import Event, EventCategory
from warden_server.models.task import Task, TaskKind, TaskStatus
from warden_server.schemas.event import EventIn
from warden_server.services.tasks import complete_task

OCCURRED_AT = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)


def _task(agent_id: uuid.UUID) -> Task:
    return Task(
        id=uuid.uuid4(),
        agent_id=agent_id,
        kind=TaskKind.WINDOW_REQUEST,
        window_start=OCCURRED_AT,
        window_end=OCCURRED_AT,
        status=TaskStatus.DISPATCHED,
        created_by="admin",
        created_at=OCCURRED_AT,
    )


def _event(**overrides) -> EventIn:
    fields = {
        "category": EventCategory.PROCESSES,
        "occurred_at": OCCURRED_AT,
        "payload": {"name": "explorer.exe", "pid": 1234},
    }
    fields.update(overrides)
    return EventIn(**fields)


def _stored_payloads(db_session, agent_id: uuid.UUID) -> list[dict]:
    rows = (
        db_session.execute(select(Event).where(Event.agent_id == agent_id))
        .scalars()
        .all()
    )
    return [row.payload for row in rows]


def test_the_same_occurrence_answered_twice_is_stored_once(db_session):
    agent_id = uuid.uuid4()
    complete_task(db_session, task=_task(agent_id), events=[_event()])
    db_session.commit()

    second = complete_task(db_session, task=_task(agent_id), events=[_event()])
    db_session.commit()

    assert second == []
    assert len(_stored_payloads(db_session, agent_id)) == 1


def test_a_different_payload_at_the_same_moment_is_kept_as_a_new_event(db_session):
    agent_id = uuid.uuid4()
    complete_task(db_session, task=_task(agent_id), events=[_event()])
    db_session.commit()

    second = complete_task(
        db_session,
        task=_task(agent_id),
        events=[_event(payload={"name": "cmd.exe", "pid": 5678})],
    )
    db_session.commit()

    assert len(second) == 1
    assert len(_stored_payloads(db_session, agent_id)) == 2


def test_the_same_payload_at_a_different_moment_is_kept_as_a_new_event(db_session):
    agent_id = uuid.uuid4()
    complete_task(db_session, task=_task(agent_id), events=[_event()])
    db_session.commit()

    later = OCCURRED_AT.replace(minute=1)
    second = complete_task(
        db_session, task=_task(agent_id), events=[_event(occurred_at=later)]
    )
    db_session.commit()

    assert len(second) == 1
    assert len(_stored_payloads(db_session, agent_id)) == 2


def test_deduplication_never_merges_two_different_stations(db_session):
    first_agent, second_agent = uuid.uuid4(), uuid.uuid4()
    complete_task(db_session, task=_task(first_agent), events=[_event()])
    db_session.commit()

    stored = complete_task(db_session, task=_task(second_agent), events=[_event()])
    db_session.commit()

    assert len(stored) == 1
    assert len(_stored_payloads(db_session, second_agent)) == 1


def test_a_fully_duplicate_batch_still_completes_the_task(db_session):
    agent_id = uuid.uuid4()
    complete_task(db_session, task=_task(agent_id), events=[_event()])
    db_session.commit()

    task = _task(agent_id)
    complete_task(db_session, task=task, events=[_event()])
    db_session.commit()

    assert task.status == TaskStatus.COMPLETED
    assert task.completed_at is not None


def test_an_empty_report_still_completes_the_task(db_session):
    task = _task(uuid.uuid4())

    stored = complete_task(db_session, task=task, events=[])
    db_session.commit()

    assert stored == []
    assert task.status == TaskStatus.COMPLETED
