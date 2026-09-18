"""Hardware/software inventory collector -- platform backend chosen at runtime."""

from warden_agent.collectors.inventory.linux import LinuxInventoryCollector
from warden_agent.collectors.inventory.windows import WindowsInventoryCollector

__all__ = ["LinuxInventoryCollector", "WindowsInventoryCollector"]
