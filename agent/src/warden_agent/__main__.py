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
from pathlib import Path

from warden_agent.buffer import Buffer
from warden_agent.collectors.registry import (
    build_collectors,
    build_inventory_collector,
    current_platform,
)
from warden_agent.config import AgentSettings, load_settings
from warden_agent.core.scheduler import AgentScheduler
from warden_agent.core.transport import ServerClient
from warden_agent.state import AgentState

logger = logging.getLogger("warden_agent")


async def enroll_if_needed(
    settings: AgentSettings, state: AgentState, client: ServerClient
) -> AgentState:
    if state.is_enrolled:
        return state
    if not settings.enrollment_token:
        raise SystemExit(
            "agent is not enrolled and no enrollment_token is configured; "
            "set enrollment_token in the config file for the first run"
        )
    hostname = settings.hostname or socket.gethostname()
    agent_id, agent_key = await client.enroll(
        token=settings.enrollment_token, hostname=hostname, os_name=current_platform()
    )
    state = AgentState(agent_id=agent_id, agent_key=agent_key)
    state.save(settings.state_path)
    logger.info("enrolled as agent %s", agent_id)
    return state


async def run(settings: AgentSettings) -> None:
    client = ServerClient(settings.server_url)
    try:
        state = await enroll_if_needed(
            settings, AgentState.load(settings.state_path), client
        )
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
        )
        await scheduler.run_forever()
    finally:
        await client.aclose()


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(prog="warden-agent")
    parser.add_argument("--config", type=Path, default=None, help="path to config.toml")
    args = parser.parse_args()

    settings = load_settings(args.config)
    asyncio.run(run(settings))


if __name__ == "__main__":
    main()
