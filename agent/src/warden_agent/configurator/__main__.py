"""`python -m warden_agent.configurator`: the tool over an explicit folder.

Works on any platform, with no service behind it. On Windows the frozen window
and the installer's helper start from `windows.main` instead, which supplies the
real service and the `%ProgramData%` folder.
"""

import sys

from warden_agent.configurator.backend import LocalBackend
from warden_agent.configurator.cli import (
    EXIT_NOT_CONNECTED,
    build_parser,
    execute,
    parse_args,
)
from warden_agent.configurator.paths import AgentPaths


def main(argv: list[str] | None = None) -> None:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    if args.config is None:
        build_parser().error("--config is required")
    backend = LocalBackend(AgentPaths.for_directory(args.config.parent))
    if args.gui:
        # Filled in with the window itself.
        raise SystemExit(EXIT_NOT_CONNECTED)
    raise SystemExit(execute(args, backend))


if __name__ == "__main__":
    main()
