"""Tests for browser profile path discovery."""

from pathlib import Path

from warden_agent.collectors.web.paths import (
    chromium_profile_candidates,
    discover_chromium_profiles,
    discover_firefox_profiles,
    firefox_profiles_root,
)


def test_chromium_candidates_use_config_dir_on_linux():
    candidates = chromium_profile_candidates(Path("/home/alice"), "linux")

    assert Path("/home/alice/.config/google-chrome/Default/History") in candidates


def test_chromium_candidates_use_appdata_on_windows():
    candidates = chromium_profile_candidates(Path("C:/Users/alice"), "windows")

    assert any("AppData" in str(path) for path in candidates)


def test_firefox_profiles_root_differs_by_os():
    linux_root = firefox_profiles_root(Path("/home/alice"), "linux")
    windows_root = firefox_profiles_root(Path("C:/Users/alice"), "windows")

    assert linux_root != windows_root
    assert ".mozilla" in str(linux_root)


def test_discover_chromium_profiles_only_returns_existing_files(tmp_path):
    (tmp_path / ".config" / "google-chrome" / "Default").mkdir(parents=True)
    (tmp_path / ".config" / "google-chrome" / "Default" / "History").write_text("")

    found = discover_chromium_profiles(tmp_path, "linux")

    assert found == [tmp_path / ".config" / "google-chrome" / "Default" / "History"]


def test_discover_firefox_profiles_globs_the_randomized_profile_folder(tmp_path):
    profile_dir = tmp_path / ".mozilla" / "firefox" / "abc123.default-release"
    profile_dir.mkdir(parents=True)
    (profile_dir / "places.sqlite").write_text("")

    found = discover_firefox_profiles(tmp_path, "linux")

    assert found == [profile_dir / "places.sqlite"]


def test_discover_firefox_profiles_returns_empty_when_root_is_missing(tmp_path):
    assert discover_firefox_profiles(tmp_path, "linux") == []
