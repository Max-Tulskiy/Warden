"""Read endpoints backing the web panel: stations, daily reports, change timeline."""

import uuid
from datetime import UTC, date, datetime, timedelta

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
        )
        .scalars()
        .all()
    )


@router.get(
    "/agents/{agent_id}/inventory/changes", response_model=list[InventoryChangeOut]
)
def inventory_changes(
    agent_id: uuid.UUID, db: Session = Depends(get_db)
) -> list[InventoryChange]:
    return list(
        db.execute(
            select(InventoryChange)
            .where(InventoryChange.agent_id == agent_id)
            .order_by(InventoryChange.detected_at.desc())
        )
        .scalars()
        .all()
    )
