"""Service entry points: how the OS starts and stops the agent process.

Both wrappers call `warden_agent.__main__.run` -- the only difference is how
the process itself is supervised: `systemd` on Linux runs the module
directly, a Windows service needs the `pywin32` service-control glue below.
"""
