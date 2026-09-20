"""Read endpoints backing the web panel: stations, daily reports, change timeline."""

import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from warden_server.api.deps import require_operator
from warden_server.db import get_db
from warden_server.models.agent import Agent
from warden_server.models.event import Event
from warden_server.models.inventory import InventoryChange
from warden_server.schemas.agent import AgentOut
from warden_server.schemas.event import EventOut
from warden_server.schemas.inventory import InventoryChangeOut
from warden_server.schemas.report import (
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    ReportEventOut,
    ReportFilter,
)

router = APIRouter(
    prefix="/api/v1", tags=["reports"], dependencies=[Depends(require_operator)]
)


@router.get("/agents", response_model=list[AgentOut])
def list_agents(db: Session = Depends(get_db)) -> list[Agent]:
    return list(db.execute(select(Agent).order_by(Agent.hostname)).scalars().all())


@router.get("/agents/{agent_id}/events", response_model=list[EventOut])
def daily_report(
    agent_id: uuid.UUID,
    report_date: date = Query(default_factory=lambda: datetime.now(UTC).date()),
    limit: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> list[Event]:
    """Events received for the station on a given day (constitution: daily reports)."""
    day_start = datetime.combine(report_date, datetime.min.time(), tzinfo=UTC)
    day_end = day_start + timedelta(days=1)
    return list(
        db.execute(
            select(Event)
            .where(
                Event.agent_id == agent_id,
                Event.occurred_at >= day_start,
                Event.occurred_at < day_end,
            )
            .order_by(Event.occurred_at)
            .limit(limit)
            .offset(offset)
        )
        .scalars()
        .all()
    )


@router.get("/events", response_model=list[ReportEventOut])
def fleet_report(
    report: Annotated[ReportFilter, Query()], db: Session = Depends(get_db)
) -> list[ReportEventOut]:
    """Events across stations for a time range, each labeled with its station.

    Reads events the server already holds, which reach it only through window
    requests (constitution principle 2) -- it is not everything the stations
    did. The range is half-open, `[start, end)`, like the window check on
    report ingestion; `id` breaks ties so offset paging stays stable when
    several events share a timestamp.
    """
    query = (
        select(Event, Agent.hostname)
        .join(Agent, Event.agent_id == Agent.id)
        .where(Event.occurred_at >= report.start, Event.occurred_at < report.end)
    )
    if report.agent_id:
        query = query.where(Event.agent_id.in_(report.agent_id))
    if report.category is not None:
        query = query.where(Event.category == report.category)

    rows = db.execute(
        query.order_by(Event.occurred_at, Event.id)
        .limit(report.limit)
        .offset(report.offset)
    ).all()
    return [
        ReportEventOut(
            id=event.id,
            category=event.category,
            occurred_at=event.occurred_at,
            payload=event.payload,
            agent_id=event.agent_id,
            hostname=hostname,
        )
        for event, hostname in rows
    ]


@router.get(
    "/agents/{agent_id}/inventory/changes", response_model=list[InventoryChangeOut]
)
def inventory_changes(
    agent_id: uuid.UUID,
    limit: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> list[InventoryChange]:
    return list(
        db.execute(
            select(InventoryChange)
            .where(InventoryChange.agent_id == agent_id)
            .order_by(InventoryChange.detected_at.desc())
            .limit(limit)
            .offset(offset)
        )
        .scalars()
        .all()
    )
