"""Operator-facing endpoint to place a window-request task on an agent."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from warden_server.api.deps import require_operator
from warden_server.db import get_db
from warden_server.models.agent import Agent
from warden_server.models.operator import Operator
from warden_server.schemas.task import TaskOut, WindowRequestIn
from warden_server.services.audit import log_event
from warden_server.services.tasks import place_window_request

router = APIRouter(prefix="/api/v1", tags=["requests"])


@router.post("/agents/{agent_id}/requests", response_model=TaskOut, status_code=201)
def create_window_request(
    agent_id: uuid.UUID,
    payload: WindowRequestIn,
    operator: Operator = Depends(require_operator),
    db: Session = Depends(get_db),
):
    """Place a request for a station's data over a bounded time window.

    `WindowRequestIn` already rejects a window over the configured maximum
    (constitution principle 3); this endpoint only needs to confirm the
    target agent exists.
    """
    agent = db.get(Agent, agent_id)
    if agent is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Unknown agent")

    task = place_window_request(
        db,
        agent_id=agent_id,
        window_start=payload.window_start,
        window_end=payload.window_end,
        created_by=operator.username,
    )
    db.flush()
    log_event(
        db,
        actor=operator.username,
        action="request.window",
        target=str(agent_id),
        detail={
            "task_id": str(task.id),
            "window_start": payload.window_start.isoformat(),
            "window_end": payload.window_end.isoformat(),
        },
    )
    db.commit()
    return task
