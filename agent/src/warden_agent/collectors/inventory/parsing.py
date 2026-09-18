"""Pure text-parsing for package-manager output.

Kept separate from the collectors that call `dpkg-query`/`rpm` so it can be
unit-tested against fixture text on any platform, not just the one that
happens to have the real tool installed (constitution principle 7).
"""

_NAME_AND_VERSION = 2


def parse_dpkg_list(output: str) -> dict[str, str]:
    """Parse `dpkg-query -W -f='${Package}\\t${Version}\\n'` output."""
    packages: dict[str, str] = {}
    for line in output.splitlines():
        parts = line.strip().split("\t", 1)
        if len(parts) == _NAME_AND_VERSION and parts[0]:
            packages[parts[0]] = parts[1]
    return packages


def parse_rpm_list(output: str) -> dict[str, str]:
    """Parse `rpm -qa --qf '%{NAME}\\t%{VERSION}-%{RELEASE}\\n'` output."""
    # Same shape as dpkg's: one "name<TAB>version" pair per line.
    return parse_dpkg_list(output)
