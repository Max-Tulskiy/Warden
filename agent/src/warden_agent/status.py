"""What the agent is doing, for the connection window to show.

The service writes this next to its state file; the window, running under an
administrator, reads it. Only codes are stored -- a state, a reason to wait, a
kind of failure -- never text from a library or a secret: the window owns the
Russian wording, and nothing here can leak a token or a key.
"""

import json
import logging
import os
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ValidationError

from warden_agent.core.transport import FailureKind
from warden_agent.errors import WaitReason

logger = logging.getLogger(__name__)


class AgentStatus(BaseModel):
    """`state` is `None` when the file does not exist yet or cannot be read."""

    state: Literal["running", "waiting"] | None = None
    detail: WaitReason | None = None
    last_success_at: datetime | None = None
    last_error: FailureKind | None = None
    last_error_at: datetime | None = None


class StatusStore:
    """Reads and writes the status file; the service is its only writer."""

    def __init__(
        self, path: Path, *, now: Callable[[], datetime] = lambda: datetime.now(UTC)
    ) -> None:
        self._path = path
        self._now = now
        self._status = self.read()

    def read(self) -> AgentStatus:
        try:
            return AgentStatus.model_validate(
                json.loads(self._path.read_text(encoding="utf-8"))
            )
        except (OSError, ValueError, ValidationError):
            return AgentStatus()

    def record_waiting(self, reason: WaitReason) -> None:
        self._write(
            self._status.model_copy(update={"state": "waiting", "detail": reason})
        )

    def record_running(self) -> None:
        self._write(
            self._status.model_copy(update={"state": "running", "detail": None})
        )

    def record_success(self) -> None:
        self._write(
            self._status.model_copy(
                update={
                    "last_success_at": self._now(),
                    "last_error": None,
                    "last_error_at": None,
                }
            )
        )

    def record_failure(self, kind: FailureKind) -> None:
        self._write(
            self._status.model_copy(
                update={"last_error": kind, "last_error_at": self._now()}
            )
        )

    def _write(self, status: AgentStatus) -> None:
        self._status = status
        temporary = self._path.with_name(self._path.name + ".tmp")
        try:
            temporary.write_text(status.model_dump_json(), encoding="utf-8")
            os.replace(temporary, self._path)
        except OSError:
            # A reader holding the file can make the replace fail on Windows.
            # The status is a courtesy to the window; it must never stop the
            # agent, so the next change simply tries again.
            logger.warning("could not write the status file %s", self._path)
            temporary.unlink(missing_ok=True)
