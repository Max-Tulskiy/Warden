"""Placing, dispatching, and completing window-request tasks.

Implements the request flow described in
`specs/001-agent-server-complex/plan.md`: an operator places a task, the
agent picks it up on its next poll, and later completes it by delivering
events.
"""

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from warden_server.models.event import Event
from warden_server.models.task import Task, TaskKind, TaskStatus
from warden_server.schemas.event import EventIn


def place_window_request(
    db: Session,
    *,
    agent_id: uuid.UUID,
    window_start: datetime,
    window_end: datetime,
    created_by: str,
) -> Task:
    task = Task(
        agent_id=agent_id,
        kind=TaskKind.WINDOW_REQUEST,
        window_start=window_start,
        window_end=window_end,
        status=TaskStatus.PENDING,
        created_by=created_by,
        created_at=datetime.now(UTC),
    )
    db.add(task)
    return task


def fetch_and_dispatch_pending(db: Session, *, agent_id: uuid.UUID) -> list[Task]:
    """Return an agent's pending tasks and mark them dispatched.

    Called from the agent-facing poll endpoint: once the agent has been
    handed a task, it is no longer offered again on the next poll, even if
    the agent never reports back (a stuck agent does not pile up duplicate
    work; principle 8's audit trail is where a missed task would surface).
    """
    tasks = list(
        db.execute(
            select(Task)
            .where(Task.agent_id == agent_id, Task.status == TaskStatus.PENDING)
            .order_by(Task.created_at)
        )
        .scalars()
        .all()
    )
    for task in tasks:
        task.status = TaskStatus.DISPATCHED
    return tasks


def _drop_already_known(
    db: Session, *, agent_id: uuid.UUID, events: list[EventIn]
) -> list[EventIn]:
    """Filter out events this station has already delivered.

    Overlapping window requests can answer with the same buffered occurrence
    more than once (specs/007-event-deduplication/spec.md R-1); an occurrence
    is the same one only if it matches on category, timestamp, and payload
    for the same station -- never across stations, and never merely because
    two events happen to be similar. Candidates are narrowed by `agent_id`
    and `occurred_at` (both indexed) before comparing category and payload in
    Python, which sidesteps writing dialect-specific JSON-equality SQL for
    SQLite's plain `JSON` column versus PostgreSQL's `JSONB`.
    """
    if not events:
        return events
    occurred_ats = {event.occurred_at for event in events}
    existing = db.execute(
        select(Event.category, Event.occurred_at, Event.payload).where(
            Event.agent_id == agent_id, Event.occurred_at.in_(occurred_ats)
        )
    ).all()
    known = {(row.category, row.occurred_at, _freeze(row.payload)) for row in existing}
    return [
        event
        for event in events
        if (event.category, event.occurred_at, _freeze(event.payload)) not in known
    ]


def _freeze(payload: dict[str, Any]) -> str:
    """A canonical, hashable string form of a JSON payload for set membership.

    A payload's shape is not fixed to flat key/value pairs (`EventIn.payload`
    is `dict[str, Any]`), so comparing it by sorted top-level items alone
    would break on a nested list or dict; `json.dumps(..., sort_keys=True)`
    canonicalizes recursively and is always hashable.
    """
    return json.dumps(payload, sort_keys=True)


def complete_task(db: Session, *, task: Task, events: list[EventIn]) -> list[Event]:
    fresh = _drop_already_known(db, agent_id=task.agent_id, events=events)
    stored = [
        Event(
            agent_id=task.agent_id,
            task_id=task.id,
            category=event.category,
            occurred_at=event.occurred_at,
            payload=event.payload,
        )
        for event in fresh
    ]
    db.add_all(stored)
    task.status = TaskStatus.COMPLETED
    task.completed_at = datetime.now(UTC)
    return stored
