"""Tests for the Windows software-inventory parsing logic.

`parse_uninstall_entries` is what actually turns raw registry values into
the software dict; it takes plain dicts shaped like what `winreg`
enumeration would produce, so it runs on every platform without `winreg`
itself ever being imported (constitution principle 7).
"""

from warden_agent.collectors.inventory.windows import parse_uninstall_entries


def test_parses_name_and_version():
    entries = [{"DisplayName": "7-Zip", "DisplayVersion": "23.01"}]

    software = parse_uninstall_entries(entries)

    assert software == {"7-Zip": "23.01"}


def test_skips_entries_without_a_display_name():
    entries = [
        {"DisplayVersion": "1.0"},  # a hotfix/registry artifact, not a program
        {"DisplayName": "Notepad++", "DisplayVersion": "8.6"},
    ]

    software = parse_uninstall_entries(entries)

    assert software == {"Notepad++": "8.6"}


def test_a_missing_version_becomes_an_empty_string():
    entries = [{"DisplayName": "Some Tool"}]

    software = parse_uninstall_entries(entries)

    assert software == {"Some Tool": ""}
