"""The command line of the connection tool: `--apply`, `--check`, and `--gui`.

`--apply` is what the installer's helper runs, and it works over any folder on
any platform. It never prompts: an authority is trusted only if the fingerprint
given in advance matches, and otherwise the fingerprint on offer is printed for
a person to compare.
"""

import argparse
import asyncio
import logging
from pathlib import Path

from warden_agent.configurator import messages
from warden_agent.configurator.backend import Backend
from warden_agent.configurator.config_file import read_config
from warden_agent.configurator.describe import describe, describe_probe
from warden_agent.configurator.logic import (
    Connected,
    ProbeKind,
    connect,
    probe,
)
from warden_agent.errors import NotConfiguredError

logger = logging.getLogger(__name__)

EXIT_CONNECTED = 0
EXIT_NOT_CONNECTED = 3


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="warden-agent-config")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--apply", action="store_true", help="connect the station")
    mode.add_argument("--check", action="store_true", help="check the address only")
    mode.add_argument("--gui", action="store_true", help="open the window")
    parser.add_argument("--server", help="address of the server")
    parser.add_argument("--token", help="one-time enrollment token")
    parser.add_argument(
        "--ca-sha256", help="expected SHA-256 of the server's authority"
    )
    parser.add_argument(
        "--replace", action="store_true", help="allow moving an enrolled station"
    )
    parser.add_argument(
        "--no-restart", action="store_true", help="do not restart the service"
    )
    parser.add_argument("--config", type=Path, help="path to the configuration file")
    return parser


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = build_parser()
    args = parser.parse_args(argv)
    if (args.apply or args.check) and not args.server:
        parser.error("--server is required with --apply and --check")
    return args


def execute(args: argparse.Namespace, backend: Backend) -> int:
    """Run `--apply` or `--check` and return the process's exit code."""
    if args.check:
        return _check(args, backend)
    return _apply(args, backend)


def run_cli(argv: list[str], backend: Backend) -> int:
    return execute(parse_args(argv), backend)


def _apply(args: argparse.Namespace, backend: Backend) -> int:
    outcome = asyncio.run(
        connect(
            backend.paths,
            server_url=args.server,
            token=args.token or "",
            expected_sha256=args.ca_sha256 or None,
            replace=args.replace,
        )
    )
    print(describe(outcome, args.server))
    if not isinstance(outcome, Connected):
        return EXIT_NOT_CONNECTED
    if not outcome.already and not args.no_restart:
        try:
            backend.restart_service()
        except Exception:
            # The station is connected and its files are saved; a service that
            # cannot be restarted here picks them up the next time it looks.
            logger.exception("could not restart the service")
    return EXIT_CONNECTED


def _check(args: argparse.Namespace, backend: Backend) -> int:
    configured = read_config(backend.paths.config).get("ca_file")
    ca_file = Path(str(configured)) if configured else None
    try:
        result = asyncio.run(probe(args.server, ca_file=ca_file))
    except NotConfiguredError:
        print(messages.REFUSED_NOT_VERIFIED)
        return EXIT_NOT_CONNECTED
    print(describe_probe(result, args.server))
    return EXIT_CONNECTED if result.kind is ProbeKind.TRUSTED else EXIT_NOT_CONNECTED
