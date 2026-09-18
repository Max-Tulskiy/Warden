"""Default browsing-history profile locations per OS.

Pure path construction, no filesystem access -- easy to test without
depending on what is actually installed on the machine running the tests.
Real discovery (globbing for the randomized Firefox profile folder name)
happens in `discover_firefox_profiles`/`discover_chromium_profiles`, which
do touch the filesystem but are exercised against a `tmp_path` layout in
tests, not against whatever the developer's own machine happens to have.
"""

from pathlib import Path


def chromium_profile_candidates(home: Path, os_name: str) -> list[Path]:
    if os_name == "windows":
        base = home / "AppData" / "Local"
        return [
            base / "Google" / "Chrome" / "User Data" / "Default" / "History",
            base / "Microsoft" / "Edge" / "User Data" / "Default" / "History",
        ]
    return [
        home / ".config" / "google-chrome" / "Default" / "History",
        home / ".config" / "chromium" / "Default" / "History",
    ]


def firefox_profiles_root(home: Path, os_name: str) -> Path:
    if os_name == "windows":
        return home / "AppData" / "Roaming" / "Mozilla" / "Firefox" / "Profiles"
    return home / ".mozilla" / "firefox"


def discover_chromium_profiles(home: Path, os_name: str) -> list[Path]:
    return [
        path for path in chromium_profile_candidates(home, os_name) if path.is_file()
    ]


def discover_firefox_profiles(home: Path, os_name: str) -> list[Path]:
    root = firefox_profiles_root(home, os_name)
    if not root.is_dir():
        return []
    return sorted(root.glob("*/places.sqlite"))
