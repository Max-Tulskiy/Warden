"""The connection window's behaviour, without any window.

The controller holds what the window shows and decides what each button does. It
imports no toolkit: the window asks it to act, an `Executor` runs the slow part
off the interface's thread, and the window redraws when the controller says its
state changed. That is what lets all of this be tested without a display.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Literal, Protocol

from warden_agent.configurator import messages
from warden_agent.configurator.backend import Backend, ServiceState
from warden_agent.configurator.config_file import read_config
from warden_agent.configurator.describe import describe, describe_probe
from warden_agent.configurator.logic import (
    ConfiguratorLog,
    Connected,
    RefusalReason,
    Refused,
    StationStatus,
    TrustNeeded,
    TrustOffer,
    begin_retrust,
    connect,
    probe,
    read_status,
    retrust,
)
from warden_agent.core.transport import FailureKind
from warden_agent.errors import NotConfiguredError

logger = logging.getLogger(__name__)

_SERVICE_TEXT = {
    ServiceState.RUNNING: messages.SERVICE_RUNNING,
    ServiceState.STOPPED: messages.SERVICE_STOPPED,
    ServiceState.NOT_INSTALLED: messages.SERVICE_NOT_INSTALLED,
    ServiceState.NOT_APPLICABLE: messages.SERVICE_NOT_APPLICABLE,
}

_WAITING_TEXT = {
    "not_configured": messages.WAITING_NOT_CONFIGURED,
    "server_changed": messages.WAITING_SERVER_CHANGED,
    "ca_unreadable": messages.WAITING_CA_UNREADABLE,
}

_ERROR_TEXT = {
    FailureKind.UNREACHABLE: messages.ERROR_UNREACHABLE,
    FailureKind.CERTIFICATE_NOT_TRUSTED: messages.ERROR_CERTIFICATE_NOT_TRUSTED,
    FailureKind.CREDENTIAL_REFUSED: messages.ERROR_CREDENTIAL_REFUSED,
    FailureKind.SERVER_ERROR: messages.ERROR_SERVER_ERROR,
    FailureKind.OTHER: messages.ERROR_OTHER,
}


class Executor(Protocol):
    """Runs a coroutine off the interface's thread and reports back on it."""

    def run(
        self, factory: Callable[[], Awaitable[Any]], on_done: Callable[[Any], None]
    ) -> None: ...


@dataclass
class WindowState:
    elevated: bool = True
    banner: str | None = None
    address: str = ""
    token: str = ""
    busy: bool = False
    message: str = ""
    message_is_error: bool = False
    status: StationStatus | None = None
    status_lines: list[tuple[str, str]] = field(default_factory=list)
    pending_trust: TrustOffer | None = None
    pending_replace: str | None = None
    offers_retrust: bool = False

    @property
    def fields_enabled(self) -> bool:
        return self.elevated and not self.busy

    @property
    def can_connect(self) -> bool:
        return self.fields_enabled and bool(self.address.strip())


class WindowController:
    def __init__(self, backend: Backend, executor: Executor) -> None:
        self._backend = backend
        self._executor = executor
        self._listeners: list[Callable[[], None]] = []
        self._trust_for: Literal["connect", "retrust"] = "connect"
        #: A move to another server that a person confirmed, remembered across
        #: the trust question that may follow it.
        self._replace_confirmed = False
        elevated = backend.is_elevated()
        self.state = WindowState(
            elevated=elevated,
            banner=None if elevated else messages.BANNER_NOT_ADMIN,
        )
        self.refresh()

    def subscribe(self, listener: Callable[[], None]) -> None:
        self._listeners.append(listener)

    # -- reading -----------------------------------------------------------

    def refresh(self) -> None:
        """Reread the station's files and the service, and redraw."""
        status = read_status(self._backend.paths, self._backend.service_state())
        self.state.status = status
        self.state.status_lines = _status_lines(status)
        self.state.offers_retrust = (
            status.enrolled
            and status.agent.last_error is FailureKind.CERTIFICATE_NOT_TRUSTED
        )
        if not self.state.address and status.configured_server:
            self.state.address = status.configured_server
        self._changed()

    def set_address(self, text: str) -> None:
        self.state.address = text
        self._changed()

    def set_token(self, text: str) -> None:
        self.state.token = text
        self._changed()

    # -- actions -----------------------------------------------------------

    def check(self) -> None:
        address = self.state.address.strip()
        ca_file = self._configured_authority()

        async def work() -> Any:
            try:
                return await probe(address, ca_file=ca_file)
            except NotConfiguredError:
                return Refused(RefusalReason.CERTIFICATE_NOT_TRUSTED)

        self._start(work, self._checked)

    def connect(self) -> None:
        self._start_connect(trust=None, replace=False)

    def begin_retrust(self) -> None:
        self._trust_for = "retrust"
        self._start(lambda: begin_retrust(self._backend.paths), self._connected)

    def answer_trust(self, accepted: bool) -> None:
        offer = self.state.pending_trust
        self.state.pending_trust = None
        if offer is None:
            return
        if not accepted:
            self._replace_confirmed = False
            self._say(messages.TRUST_NOT_GIVEN, error=True)
            return
        if self._trust_for == "retrust":
            self._start(self._retrust_flow(offer), self._retrusted)
        else:
            self._start_connect(trust=offer, replace=self._replace_confirmed)

    def answer_replace(self, accepted: bool) -> None:
        self.state.pending_replace = None
        self._replace_confirmed = accepted
        if accepted:
            self._start_connect(trust=None, replace=True)
        else:
            self._changed()

    # -- the slow part -----------------------------------------------------

    def _start_connect(self, *, trust: TrustOffer | None, replace: bool) -> None:
        address, token = self.state.address, self.state.token
        self._trust_for = "connect"

        async def work() -> Any:
            outcome = await connect(
                self._backend.paths,
                server_url=address,
                token=token,
                trust=trust,
                replace=replace,
            )
            if isinstance(outcome, Connected) and not outcome.already:
                await asyncio.to_thread(self._restart_service)
            return outcome

        self._start(work, self._connected)

    def _retrust_flow(self, offer: TrustOffer) -> Callable[[], Awaitable[Any]]:
        async def work() -> Any:
            outcome = await retrust(self._backend.paths, offer=offer)
            if isinstance(outcome, Connected):
                await asyncio.to_thread(self._restart_service)
            return outcome

        return work

    def _restart_service(self) -> None:
        try:
            self._backend.restart_service()
        except Exception:
            # The files are saved; a service that cannot be restarted from here
            # rereads them the next time it looks.
            logger.exception("could not restart the service")

    def _start(
        self, factory: Callable[[], Awaitable[Any]], handler: Callable[[Any], None]
    ) -> None:
        if self.state.busy or not self.state.elevated:
            return
        self.state.busy = True
        self.state.message = ""
        self._changed()
        self._executor.run(factory, lambda result: self._finished(handler, result))

    def _finished(self, handler: Callable[[Any], None], result: Any) -> None:
        self.state.busy = False
        if isinstance(result, BaseException):
            logger.error("the window's action failed", exc_info=result)
            ConfiguratorLog(self._backend.paths.log).write(
                "failed", error=type(result).__name__
            )
            self._say(messages.UNEXPECTED_FAILURE, error=True)
        else:
            handler(result)
        self.refresh()

    # -- what each result means -------------------------------------------

    def _checked(self, result: Any) -> None:
        if isinstance(result, Refused):
            self._say(describe(result, self.state.address), error=True)
            return
        self._say(
            describe_probe(result, self.state.address),
            error=result.kind.value != "trusted",
        )

    def _connected(self, outcome: Any) -> None:
        if not isinstance(outcome, TrustNeeded):
            self._replace_confirmed = False
        if isinstance(outcome, TrustNeeded):
            self.state.pending_trust = outcome.offer
        elif isinstance(outcome, Refused) and (
            outcome.reason is RefusalReason.NEEDS_REPLACE
        ):
            self.state.pending_replace = outcome.current_server
        elif isinstance(outcome, Connected):
            self.set_token("")
            self._say(describe(outcome, self.state.address))
        else:
            self._say(describe(outcome, self.state.address), error=True)

    def _retrusted(self, outcome: Any) -> None:
        if isinstance(outcome, Connected):
            self._say(messages.TRUST_UPDATED.format(server=outcome.server_url))
        else:
            self._say(describe(outcome, self.state.address), error=True)

    # -- helpers -----------------------------------------------------------

    def _configured_authority(self) -> Path | None:
        configured = read_config(self._backend.paths.config).get("ca_file")
        return Path(str(configured)) if configured else None

    def _say(self, text: str, *, error: bool = False) -> None:
        self.state.message = text
        self.state.message_is_error = error
        self._changed()

    def _changed(self) -> None:
        for listener in self._listeners:
            listener()


def _status_lines(status: StationStatus) -> list[tuple[str, str]]:
    agent = status.agent
    if agent.state == "running":
        agent_text = messages.AGENT_RUNNING
    elif agent.state == "waiting" and agent.detail is not None:
        agent_text = _WAITING_TEXT[agent.detail]
    else:
        agent_text = messages.AGENT_UNKNOWN
    station = (
        messages.STATION_ENROLLED.format(server=status.enrolled_server)
        if status.enrolled
        else messages.STATION_NOT_ENROLLED
    )
    return [
        (messages.LABEL_SERVICE, _SERVICE_TEXT[status.service]),
        (messages.LABEL_AGENT, agent_text),
        (messages.LABEL_STATION, station),
        (messages.LABEL_LAST_CONTACT, _when(agent.last_success_at)),
        (
            messages.LABEL_LAST_ERROR,
            messages.LAST_ERROR_NONE
            if agent.last_error is None
            else _ERROR_TEXT[agent.last_error],
        ),
    ]


def _when(moment: datetime | None) -> str:
    if moment is None:
        return messages.LAST_CONTACT_NEVER
    return moment.astimezone().strftime("%d.%m.%Y, %H:%M")
