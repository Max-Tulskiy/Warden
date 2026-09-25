"""`python -m warden_agent.configurator`: the tool over an explicit folder.

Works on any platform, with no service behind it. On Windows the frozen window
and the installer's helper start from `windows.main` instead, which supplies the
real service and the `%ProgramData%` folder.
"""

import sys

from warden_agent.configurator.backend import LocalBackend
from warden_agent.configurator.cli import (
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
        # Qt is imported only when the window is asked for, so the command line
        # works on a machine that does not have it.
        from warden_agent.configurator.view import run_window  # noqa: PLC0415

        raise SystemExit(run_window(backend))
    raise SystemExit(execute(args, backend))


if __name__ == "__main__":
    main()
