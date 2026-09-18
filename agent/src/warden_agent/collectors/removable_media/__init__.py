"""Removable-media connect/disconnect collector.

The platform backend is chosen at runtime.
"""

from warden_agent.collectors.removable_media.linux import LinuxRemovableMediaCollector
from warden_agent.collectors.removable_media.windows import (
    WindowsRemovableMediaCollector,
)

__all__ = ["LinuxRemovableMediaCollector", "WindowsRemovableMediaCollector"]
