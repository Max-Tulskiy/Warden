"""Persisted enrollment state: the agent id and key issued at enrollment.

Kept separate from `AgentSettings` because it is written by the agent itself
(after a successful enroll), not by whoever deploys the configuration file.
"""

import json
from pathlib import Path

from pydantic import BaseModel


class AgentState(BaseModel):
    agent_id: str | None = None
    agent_key: str | None = None

    @property
    def is_enrolled(self) -> bool:
        return self.agent_id is not None and self.agent_key is not None

    @classmethod
    def load(cls, path: Path) -> "AgentState":
        if not path.exists():
            return cls()
        return cls.model_validate_json(path.read_text(encoding="utf-8"))

    def save(self, path: Path) -> None:
        path.write_text(json.dumps(self.model_dump()), encoding="utf-8")
        path.chmod(0o600)
