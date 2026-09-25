"""Persisted enrollment state: the agent id and key issued at enrollment.

Kept separate from `AgentSettings` because it is written by the agent itself
(after a successful enroll), not by whoever deploys the configuration file.
"""

import json
from pathlib import Path

from pydantic import BaseModel


def _same_server(a: str, b: str) -> bool:
    return a.rstrip("/").casefold() == b.rstrip("/").casefold()


class AgentState(BaseModel):
    agent_id: str | None = None
    agent_key: str | None = None
    #: The server the key was issued by. A key means nothing to any other
    #: server, so an agent whose configuration names a different one is not
    #: enrolled there. Absent in a state written by an earlier version, which
    #: is then accepted as it is.
    server_url: str | None = None

    @property
    def is_enrolled(self) -> bool:
        return self.agent_id is not None and self.agent_key is not None

    def is_enrolled_for(self, server_url: str) -> bool:
        if not self.is_enrolled:
            return False
        return self.server_url is None or _same_server(self.server_url, server_url)

    @classmethod
    def load(cls, path: Path) -> "AgentState":
        if not path.exists():
            return cls()
        return cls.model_validate_json(path.read_text(encoding="utf-8"))

    def save(self, path: Path) -> None:
        path.write_text(json.dumps(self.model_dump()), encoding="utf-8")
        path.chmod(0o600)
