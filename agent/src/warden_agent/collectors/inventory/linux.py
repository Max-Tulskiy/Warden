"""Linux inventory backend: hardware via `psutil`, software via the package manager.

Prefers `dpkg-query` (Debian/Ubuntu); falls back to `rpm` (RHEL/Fedora/ALT).
If neither tool is present or the call fails, software inventory comes back
empty rather than raising -- a station this agent can still enroll and
observe otherwise should not go dark entirely over one missing tool.
"""

import asyncio
import shutil
import subprocess
from typing import Any

from warden_agent.collectors.inventory.hardware import collect_hardware
from warden_agent.collectors.inventory.parsing import parse_dpkg_list, parse_rpm_list

_DPKG_FORMAT = "${Package}\t${Version}\n"
_RPM_FORMAT = "%{NAME}\t%{VERSION}-%{RELEASE}\n"
_COMMAND_TIMEOUT_SECONDS = 30


class LinuxInventoryCollector:
    async def snapshot(self) -> tuple[dict[str, Any], dict[str, Any]]:
        return await asyncio.to_thread(self._snapshot_sync)

    def _snapshot_sync(self) -> tuple[dict[str, Any], dict[str, str]]:
        return collect_hardware(), self._collect_software()

    def _collect_software(self) -> dict[str, str]:
        if shutil.which("dpkg-query"):
            output = self._run(["dpkg-query", "-W", f"-f={_DPKG_FORMAT}"])
            if output is not None:
                return parse_dpkg_list(output)
        if shutil.which("rpm"):
            output = self._run(["rpm", "-qa", "--qf", _RPM_FORMAT])
            if output is not None:
                return parse_rpm_list(output)
        return {}

    @staticmethod
    def _run(command: list[str]) -> str | None:
        try:
            result = subprocess.run(  # noqa: S603 -- fixed command list, no shell, no untrusted input  # nosec B603
                command,
                capture_output=True,
                text=True,
                check=False,
                timeout=_COMMAND_TIMEOUT_SECONDS,
            )
        except (OSError, subprocess.TimeoutExpired):
            return None
        return result.stdout if result.returncode == 0 else None
