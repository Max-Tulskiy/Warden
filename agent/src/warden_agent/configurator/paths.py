"""Where the agent keeps its files: one folder, protected as a whole."""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AgentPaths:
    """The agent's files, all inside one folder.

    On Windows the installer restricts that folder to SYSTEM and
    Administrators, so what the connection window writes here is protected the
    same way as the rest of the agent's data.
    """

    directory: Path

    @classmethod
    def for_directory(cls, directory: Path | str) -> "AgentPaths":
        return cls(Path(directory))

    @property
    def config(self) -> Path:
        return self.directory / "config.toml"

    @property
    def authority(self) -> Path:
        """The certificate authority the administrator chose to trust."""
        return self.directory / "server-ca.pem"

    @property
    def state(self) -> Path:
        return self.directory / "state.json"

    @property
    def status(self) -> Path:
        return self.directory / "status.json"

    @property
    def log(self) -> Path:
        return self.directory / "configurator.log"
