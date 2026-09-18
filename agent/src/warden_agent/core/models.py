"""Wire-shape data structures shared by transport and scheduler.

Deliberately plain dataclasses, not a copy of the server's Pydantic schemas:
the agent and the server are separately distributed modules (constitution
Section II), so each side owns its own view of the contract in
`contracts/openapi.yaml` rather than importing the other's code.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class TaskDTO:
    id: str
    kind: str
    window_start: datetime
    window_end: datetime
    status: str


@dataclass(frozen=True)
class OutgoingEvent:
    category: str
    occurred_at: datetime
    payload: dict[str, Any]
