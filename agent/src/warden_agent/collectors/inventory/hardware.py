"""Hardware snapshot: cross-platform via `psutil`, no OS split needed.

Like the process collector, this needs no `linux.py`/`windows.py` split --
`psutil` and the standard library's `platform` module already normalize CPU,
memory, and disk information across operating systems.
"""

import platform
from typing import Any

import psutil


def collect_hardware() -> dict[str, Any]:
    memory = psutil.virtual_memory()
    disks = []
    for partition in psutil.disk_partitions(all=False):
        try:
            usage = psutil.disk_usage(partition.mountpoint)
        except OSError:
            continue  # an unmounted or inaccessible partition, skip it
        disks.append(
            {
                "device": partition.device,
                "mountpoint": partition.mountpoint,
                "filesystem": partition.fstype,
                "total_bytes": usage.total,
            }
        )

    return {
        "cpu_model": platform.processor() or platform.machine(),
        "cpu_count": psutil.cpu_count(logical=True) or 0,
        "memory_total_bytes": memory.total,
        "disks": disks,
        "os": platform.system(),
        "os_version": platform.version(),
    }
