"""Where the agent keeps its files: one folder, protected as a whole."""

from dataclasses import dataclass, replace
from pathlib import Path

from warden_agent.configurator.config_file import read_config


@dataclass(frozen=True)
class AgentPaths:
    """The agent's files, all inside one folder unless the configuration moves some.

    On Windows the installer restricts that folder to SYSTEM and
    Administrators, so what the connection window writes here is protected the
    same way as the rest of the agent's data.

    The agent reads its state from the `state_path` in its configuration, which
    on Linux is not beside the configuration file, so the state and the status
    file (which the agent keeps next to it) follow that setting when it is there.
    """

    directory: Path
    state_path: Path | None = None

    @classmethod
    def for_directory(cls, directory: Path | str) -> "AgentPaths":
        return cls(Path(directory))

    def following_config(self) -> "AgentPaths":
        """These paths, with the state where the configuration says it is."""
        configured = read_config(self.config).get("state_path")
        if not configured:
            return self
        return replace(self, state_path=Path(str(configured)))

    @property
    def config(self) -> Path:
        return self.directory / "config.toml"

    @property
    def authority(self) -> Path:
        """The certificate authority the administrator chose to trust."""
        return self.directory / "server-ca.pem"

    @property
    def state(self) -> Path:
        return self.state_path or self.directory / "state.json"

    @property
    def status(self) -> Path:
        # The agent writes it beside its state file.
        return self.state.parent / "status.json"

    @property
    def log(self) -> Path:
        return self.directory / "configurator.log"
