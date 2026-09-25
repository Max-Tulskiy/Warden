"""What the connection window needs from the operating system.

The window and the installer's helper reach the machine only through this
protocol, so the same code runs over a Windows service, over nothing at all (a
development folder), and over a stand-in in tests.
"""

from enum import StrEnum
from typing import Protocol

from warden_agent.configurator.paths import AgentPaths


class ServiceState(StrEnum):
    RUNNING = "running"
    STOPPED = "stopped"
    NOT_INSTALLED = "not_installed"
    #: There is no service to ask about (a development folder, a test).
    NOT_APPLICABLE = "not_applicable"


class Backend(Protocol):
    @property
    def paths(self) -> AgentPaths:
        """The folder the agent keeps its files in."""
        ...

    def is_elevated(self) -> bool:
        """Whether this process may change the agent's files and its service."""
        ...

    def service_state(self) -> ServiceState: ...

    def restart_service(self) -> None:
        """Restart the service if it is running, so it rereads what was saved."""
        ...
