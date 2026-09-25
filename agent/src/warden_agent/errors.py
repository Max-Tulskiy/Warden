"""Errors shared by the agent's entry points and the connection window."""

from typing import Literal

#: Why an agent that is waiting is waiting; the codes the status file stores.
WaitReason = Literal["not_configured", "server_changed", "ca_unreadable"]


class NotConfiguredError(RuntimeError):
    """The agent has nothing to connect with yet.

    Raised when it is neither enrolled nor holding a token to enroll with, when
    it is enrolled with a different server than the one configured, or when the
    trust anchor named in its configuration cannot be used. It is not a crash:
    the agent waits and looks again, so it starts working as soon as an
    administrator finishes configuring it.
    """

    def __init__(self, message: str, reason: WaitReason = "not_configured") -> None:
        super().__init__(message)
        self.reason: WaitReason = reason
