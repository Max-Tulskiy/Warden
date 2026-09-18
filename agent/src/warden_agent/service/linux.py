"""Linux service entry point.

No systemd-specific code is needed here: a `Type=simple` unit
(`packaging/systemd/warden-agent.service`) runs `python -m warden_agent`
directly, and systemd itself handles start/stop/restart. This module exists
so that entry point has a single, documented home rather than being spread
across the packaging config's `ExecStart` line.
"""

from warden_agent.__main__ import main

if __name__ == "__main__":
    main()
