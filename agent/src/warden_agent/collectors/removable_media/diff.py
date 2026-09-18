"""Pure connect/disconnect diffing, shared by both platform backends.

Kept separate so the "what changed since last time" logic -- the actual
substance of this category -- is tested once, directly, rather than only
indirectly through each platform's own enumeration mechanism.
"""


def diff_devices(previous: set[str], current: set[str]) -> list[tuple[str, str]]:
    """Return `(device, action)` pairs for everything that changed, sorted for
    a deterministic event order."""
    changes = [(device, "connected") for device in sorted(current - previous)]
    changes += [(device, "disconnected") for device in sorted(previous - current)]
    return changes
