"""Command-line entry point: `python -m warden_agent` / the `warden-agent` script.

Loads configuration, enrolls if this is the station's first run, builds the
platform's collectors, and runs the scheduler until interrupted. Service
wrappers (`service/linux.py`, `service/windows.py`) call `run()` the same
way; only how the process itself is started and stopped differs between a
systemd unit and a Windows service.
"""

import argparse
import asyncio
import logging
import socket
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Final

from warden_agent.buffer import Buffer
from warden_agent.collectors.registry import (
    build_collectors,
    build_inventory_collector,
    current_platform,
)
from warden_agent.config import AgentSettings, load_settings
from warden_agent.core.scheduler import AgentScheduler
from warden_agent.core.transport import ServerClient, build_ssl_context
from warden_agent.errors import NotConfiguredError
from warden_agent.state import AgentState
from warden_agent.status import StatusStore

logger = logging.getLogger("warden_agent")

#: How often an agent that is not configured yet looks again. It bounds how
#: long a station takes to start working once an administrator has connected
#: it, well inside the minute the connection window promises.
CONFIG_RECHECK_SECONDS: Final = 30


async def enroll_if_needed(
    settings: AgentSettings, state: AgentState, client: ServerClient
) -> AgentState:
    if state.is_enrolled_for(settings.server_url):
        return state
    if not settings.enrollment_token:
        if state.is_enrolled:
            raise NotConfiguredError(
                f"enrolled with {state.server_url}, but configured for "
                f"{settings.server_url}; enroll again to use the new server",
                reason="server_changed",
            )
        raise NotConfiguredError(
            "agent is not enrolled and no enrollment_token is configured; "
            "connect it to a server with the configuration window, or set "
            "enrollment_token in the config file"
        )
    hostname = settings.hostname or socket.gethostname()
    agent_id, agent_key = await client.enroll(
        token=settings.enrollment_token, hostname=hostname, os_name=current_platform()
    )
    state = AgentState(
        agent_id=agent_id, agent_key=agent_key, server_url=settings.server_url
    )
    state.save(settings.state_path)
    logger.info("enrolled as agent %s", agent_id)
    return state


async def wait_until_configured(
    settings: AgentSettings,
    *,
    reload_settings: Callable[[], AgentSettings],
    status: StatusStore,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> tuple[AgentSettings, AgentState, ServerClient]:
    """Return once the agent has a server to talk to and a key for it.

    An agent that is not configured yet is not a failure: it says why in its
    status and looks again every `CONFIG_RECHECK_SECONDS`, rereading the
    configuration and the state, which the connection window rewrites. The
    caller owns the returned client.
    """
    while True:
        client: ServerClient | None = None
        try:
            client = ServerClient(
                settings.server_url, verify=build_ssl_context(settings.ca_file)
            )
            state = await enroll_if_needed(
                settings, AgentState.load(settings.state_path), client
            )
        except NotConfiguredError as waiting:
            logger.warning(
                "%s; looking again in %d seconds", waiting, CONFIG_RECHECK_SECONDS
            )
            status.record_waiting(waiting.reason)
            if client is not None:
                await client.aclose()
            await sleep(CONFIG_RECHECK_SECONDS)
            settings = reload_settings()
            continue
        except BaseException:
            if client is not None:
                await client.aclose()
            raise
        return settings, state, client


async def run(
    settings: AgentSettings, *, reload_settings: Callable[[], AgentSettings]
) -> None:
    status = StatusStore(settings.state_path.parent / "status.json")
    settings, state, client = await wait_until_configured(
        settings, reload_settings=reload_settings, status=status
    )
    try:
        if state.agent_id is None or state.agent_key is None:
            raise RuntimeError("enrollment did not produce an agent id/key")

        scheduler = AgentScheduler(
            client=client,
            buffer=Buffer(settings.buffer_path),
            collectors=build_collectors(home=Path.home()),
            inventory_collector=build_inventory_collector(),
            agent_id=state.agent_id,
            agent_key=state.agent_key,
            poll_interval_seconds=settings.poll_interval_seconds,
            inventory_interval_seconds=settings.inventory_interval_seconds,
            retention_hours=settings.retention_hours,
            max_window_hours=4,
            status=status,
        )
        status.record_running()
        await scheduler.run_forever()
    finally:
        await client.aclose()


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(prog="warden-agent")
    parser.add_argument("--config", type=Path, default=None, help="path to config.toml")
    args = parser.parse_args()

    asyncio.run(
        run(
            load_settings(args.config),
            reload_settings=lambda: load_settings(args.config),
        )
    )


if __name__ == "__main__":
    main()
