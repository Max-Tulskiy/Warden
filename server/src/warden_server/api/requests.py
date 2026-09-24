"""Operator-facing endpoint to place a window-request task on an agent."""

import uuid
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from warden_server.api.deps import ADMIN_ONLY_RESPONSES, require_admin
from warden_server.db import get_db
from warden_server.models.agent import Agent
from warden_server.models.operator import Operator
from warden_server.schemas.task import TaskOut, WindowRequestIn
from warden_server.services.audit import log_event
from warden_server.services.policy import effective_policy
from warden_server.services.tasks import place_window_request

router = APIRouter(prefix="/api/v1", tags=["requests"])


@router.post(
    "/agents/{agent_id}/requests",
    response_model=TaskOut,
    status_code=201,
    responses=ADMIN_ONLY_RESPONSES,
)
def create_window_request(
    agent_id: uuid.UUID,
    payload: WindowRequestIn,
    operator: Operator = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Place a request for a station's data over a bounded time window.

    `WindowRequestIn` already rejects a window over the four-hour ceiling
    (constitution principle 3), with no database; this endpoint additionally
    holds the window to the limit in force, which an administrator may have
    lowered, and confirms the target agent exists. A request placed before the
    limit was lowered stays as it was placed.
    """
    agent = db.get(Agent, agent_id)
    if agent is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Unknown agent")

    limit = effective_policy(db).max_request_window_hours
    if payload.window_end - payload.window_start > timedelta(hours=limit):
        raise HTTPException(
            422,
            detail=f"The request window must not exceed {limit} hours",
        )

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
