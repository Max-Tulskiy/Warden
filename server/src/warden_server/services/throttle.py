"""In-process fixed-window failure counter for operator login (CWE-307).

Keyed on the attempted username rather than the client's network
address: behind the Caddy proxy the peer address seen by FastAPI is
Caddy itself unless forwarded-header trust is configured, while the
username is exactly what needs protecting from repeated expensive
Argon2id verification.

State lives in this process's memory. `server/Dockerfile` starts
uvicorn without `--workers`, so for the shipped deployment this counter
is accurate; running multiple workers or replicas would multiply the
effective limit, and a restart clears it. Documented as a known
limitation rather than solved here (constitution principle 10) -- the
real fix for a multi-process deployment is a limit enforced in front
of the server, not in it.
"""

import threading
import time

MAX_ATTEMPTS = 5
WINDOW_SECONDS = 300.0

_lock = threading.Lock()
_failures: dict[str, list[float]] = {}


def _recent_failures(key: str, now: float) -> list[float]:
    return [t for t in _failures.get(key, []) if now - t < WINDOW_SECONDS]


def is_throttled(key: str) -> bool:
    now = time.monotonic()
    with _lock:
        recent = _recent_failures(key, now)
        _failures[key] = recent
        return len(recent) >= MAX_ATTEMPTS


def record_failure(key: str) -> None:
    now = time.monotonic()
    with _lock:
        _failures[key] = [*_recent_failures(key, now), now]


def reset(key: str) -> None:
    with _lock:
        _failures.pop(key, None)


def clear_all() -> None:
    """Test-only: drop all state so login-throttle tests don't leak."""
    with _lock:
        _failures.clear()
