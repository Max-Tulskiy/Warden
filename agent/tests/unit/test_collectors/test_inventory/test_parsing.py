"""Tests for parsing `dpkg-query`/`rpm` package-list output (fixture text)."""

from warden_agent.collectors.inventory.parsing import parse_dpkg_list, parse_rpm_list


def test_parse_dpkg_list_reads_name_and_version():
    output = "bash\t5.2.15-2+b2\ncurl\t8.5.0-2\n"

    packages = parse_dpkg_list(output)

    assert packages == {"bash": "5.2.15-2+b2", "curl": "8.5.0-2"}


def test_parse_dpkg_list_skips_blank_and_malformed_lines():
    output = "bash\t5.2.15-2+b2\n\nmalformed-line-without-a-tab\n"

    packages = parse_dpkg_list(output)

    assert packages == {"bash": "5.2.15-2+b2"}


def test_parse_rpm_list_reads_name_and_version():
    output = "glibc\t2.38-6.fc39\n"

    packages = parse_rpm_list(output)

    assert packages == {"glibc": "2.38-6.fc39"}
