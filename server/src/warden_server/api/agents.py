"""Agent-facing endpoints: enrollment, task polling, report and inventory upload.

Together these implement the active-agent model of constitution D-1: the
agent is always the one initiating a request; nothing here pushes to the
agent. The operator-facing endpoints in this module (enrollment tokens,
enabling/disabling a station) only change server-side state.
"""

import uuid
from datetime import UTC, datetime, timedelta
from typing import cast

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import update
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session

from warden_server.api.deps import ADMIN_ONLY_RESPONSES, require_admin, require_agent
from warden_server.db import get_db
from warden_server.models.agent import Agent, AgentStatus
from warden_server.models.enrollment import EnrollmentToken
from warden_server.models.operator import Operator
from warden_server.models.task import Task, TaskStatus
from warden_server.schemas.agent import (
    AgentOut,
    AgentStatusIn,
    EnrollRequest,
    EnrollResponse,
)
from warden_server.schemas.enrollment import EnrollmentTokenOut
from warden_server.schemas.event import ReportIn
from warden_server.schemas.inventory import InventoryIn
from warden_server.schemas.task import TaskOut
from warden_server.security import generate_secret_token, hash_secret_token
from warden_server.services import tasks as tasks_service
from warden_server.services.audit import log_event
from warden_server.services.inventory import ingest_snapshot
from warden_server.services.policy import effective_policy

router = APIRouter(prefix="/api/v1", tags=["agents"])


@router.post(
    "/enrollment-tokens",
    response_model=EnrollmentTokenOut,
    status_code=201,
    responses=ADMIN_ONLY_RESPONSES,
)
def create_enrollment_token(
    operator: Operator = Depends(require_admin), db: Session = Depends(get_db)
) -> EnrollmentTokenOut:
    """Issue a one-time token an administrator hands to a new agent."""
    token = generate_secret_token()
    now = datetime.now(UTC)
    expires_at = now + timedelta(hours=effective_policy(db).enrollment_token_ttl_hours)
    db.add(
        EnrollmentToken(
            token_hash=hash_secret_token(token),
            created_by=operator.username,
            created_at=now,
            expires_at=expires_at,
        )
    )
    log_event(db, actor=operator.username, action="enrollment_token.create", target="-")
    db.commit()
    return EnrollmentTokenOut(token=token, expires_at=expires_at)


@router.post("/enroll", response_model=EnrollResponse, status_code=201)
def enroll(payload: EnrollRequest, db: Session = Depends(get_db)) -> EnrollResponse:
    """Register a new agent against a one-time enrollment token."""
    token_hash = hash_secret_token(payload.token)
    now = datetime.now(UTC)
    invalid_token = HTTPException(
        status.HTTP_400_BAD_REQUEST, detail="Invalid or used token"
    )

    # Claimed with a single conditional UPDATE rather than a SELECT
    # followed by a Python-side check, so two concurrent requests for the
    # same token cannot both observe it as unused (CWE-362): only one
    # UPDATE can ever match the `used_at IS NULL` row, and `rowcount`
    # tells the loser it lost the race.
    claimed = cast(
        CursorResult,
        db.execute(
            update(EnrollmentToken)
            .where(
                EnrollmentToken.token_hash == token_hash,
                EnrollmentToken.used_at.is_(None),
                EnrollmentToken.expires_at >= now,
            )
            .values(used_at=now)
            .execution_options(synchronize_session=False)
        ),
    )
    if claimed.rowcount != 1:
        log_event(
            db, actor=payload.hostname, action="agent.enroll_rejected", target="-"
        )
        db.commit()
        raise invalid_token

    agent_key = generate_secret_token()
    agent = Agent(
        hostname=payload.hostname,
        os=payload.os,
        agent_key_hash=hash_secret_token(agent_key),
        status=AgentStatus.ACTIVE,
        enrolled_at=now,
        last_seen_at=now,
    )
    db.add(agent)
    db.flush()  # populate agent.id before it is used in the audit log/response
    log_event(
        db,
        actor=payload.hostname,
        action="agent.enroll",
        target=str(agent.id),
        detail={"os": payload.os},
    )
    db.commit()
    return EnrollResponse(agent_id=agent.id, agent_key=agent_key)


@router.patch(
    "/agents/{agent_id}", response_model=AgentOut, responses=ADMIN_ONLY_RESPONSES
)
def set_agent_status(
    agent_id: uuid.UUID,
    payload: AgentStatusIn,
    operator: Operator = Depends(require_admin),
    db: Session = Depends(get_db),
) -> Agent:
    """Enable or disable a station.

    Enforcement lives in `require_agent`, which rejects any agent that is not
    `ACTIVE` exactly as it rejects a wrong key; this endpoint only flips the
    flag. Setting the current status again is a no-op and is not audited.
    """
    agent = db.get(Agent, agent_id)
    if agent is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Unknown agent")

    if agent.status != payload.status:
        agent.status = payload.status
        log_event(
            db,
            actor=operator.username,
            action=(
                "agent.disabled"
                if payload.status == AgentStatus.DISABLED
                else "agent.enabled"
            ),
            target=str(agent.id),
            detail={"hostname": agent.hostname},
        )
        db.commit()
    return agent


@router.get("/agents/{agent_id}/tasks", response_model=list[TaskOut])
def poll_tasks(
    agent: Agent = Depends(require_agent), db: Session = Depends(get_db)
) -> list[Task]:
    """Return an agent's pending tasks and mark them dispatched."""
    agent.last_seen_at = datetime.now(UTC)
    pending = tasks_service.fetch_and_dispatch_pending(db, agent_id=agent.id)
    if pending:
        log_event(
            db,
            actor=str(agent.id),
            action="agent.tasks_dispatched",
            target=str(agent.id),
            detail={"task_ids": [str(task.id) for task in pending]},
        )
    db.commit()
    return pending


@router.post("/agents/{agent_id}/reports", status_code=204, response_class=Response)
def submit_report(
    payload: ReportIn,
    agent: Agent = Depends(require_agent),
    db: Session = Depends(get_db),
) -> Response:
    """Accept an agent's answer to a previously dispatched window-request task."""
    task = db.get(Task, payload.task_id)
    if task is None or task.agent_id != agent.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Unknown task")
    if task.status != TaskStatus.DISPATCHED:
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail="Task is not awaiting a report"
        )

    outside_window = [
        event
        for event in payload.events
        if not (task.window_start <= event.occurred_at < task.window_end)
    ]
    if outside_window:
        log_event(
            db,
            actor=str(agent.id),
            action="agent.report_out_of_window",
            target=str(task.id),
            detail={
                "rejected": len(outside_window),
                "total": len(payload.events),
            },
        )
        db.commit()
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="Report contains events outside the requested window",
        )

    stored = tasks_service.complete_task(db, task=task, events=payload.events)
    agent.last_seen_at = datetime.now(UTC)
    log_event(
        db,
        actor=str(agent.id),
        action="agent.report",
        target=str(task.id),
        detail={"event_count": len(payload.events), "new_count": len(stored)},
    )
    db.commit()
    return Response(status_code=204)


@router.post("/agents/{agent_id}/inventory", status_code=204, response_class=Response)
def submit_inventory(
    payload: InventoryIn,
    agent: Agent = Depends(require_agent),
    db: Session = Depends(get_db),
) -> Response:
    """Accept a periodic inventory snapshot; doubles as the agent's heartbeat."""
    agent.last_seen_at = datetime.now(UTC)
    log_event(
        db, actor=str(agent.id), action="agent.inventory_snapshot", target=str(agent.id)
    )
    change = ingest_snapshot(
        db, agent_id=agent.id, hardware=payload.hardware, software=payload.software
    )
    if change is not None:
        log_event(
            db,
            actor=str(agent.id),
            action="agent.inventory_change",
            target=str(agent.id),
            detail={"change_id": str(change.id)},
        )
    db.commit()
    return Response(status_code=204)
