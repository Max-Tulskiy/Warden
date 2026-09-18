"""Placing, dispatching, and completing window-request tasks.

Implements the request flow described in
`specs/001-agent-server-complex/plan.md`: an operator places a task, the
agent picks it up on its next poll, and later completes it by delivering
events.
"""

import uuid
from datetime import UTC, datetime

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


def complete_task(db: Session, *, task: Task, events: list[EventIn]) -> list[Event]:
    stored = [
        Event(
            agent_id=task.agent_id,
            task_id=task.id,
            category=event.category,
            occurred_at=event.occurred_at,
            payload=event.payload,
        )
        for event in events
    ]
    db.add_all(stored)
    task.status = TaskStatus.COMPLETED
    task.completed_at = datetime.now(UTC)
    return stored
