"""Shared Arc and Zen profile path resolution helpers."""

from __future__ import annotations

import configparser
import json
import os
import sys
from pathlib import Path
from typing import Iterable, Optional


def default_arc_profile_path() -> Path:
    discovered = discover_arc_profiles()
    if discovered:
        return discovered[0]

    if sys.platform == "win32":
        return (
            Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
            / "Packages"
            / "TheBrowserCompany.Arc_ttt1ap7aakyb4"
            / "LocalCache"
            / "Local"
            / "Arc"
        )
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Arc"

    # Arc desktop does not currently have a known Linux profile location.
    # Return a harmless fallback so callers get a concrete validation error.
    return Path.home() / ".arc"


def _arc_candidate_roots() -> list[Path]:
    if sys.platform == "darwin":
        return [Path.home() / "Library" / "Application Support" / "Arc"]

    if sys.platform == "win32":
        local_app_data = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        packages = local_app_data / "Packages"
        exact = packages / "TheBrowserCompany.Arc_ttt1ap7aakyb4" / "LocalCache" / "Local" / "Arc"
        wildcard = sorted(packages.glob("TheBrowserCompany.Arc_*"))
        return [exact] + [path / "LocalCache" / "Local" / "Arc" for path in wildcard if path.name != "TheBrowserCompany.Arc_ttt1ap7aakyb4"]

    return []


def is_sqlite_database(path: Path) -> bool:
    if not path.exists() or not path.is_file():
        return False
    try:
        with open(path, "rb") as f:
            return f.read(16) == b"SQLite format 3\x00"
    except OSError:
        return False


def is_json_file(path: Path) -> bool:
    if not path.exists() or not path.is_file():
        return False
    try:
        with open(path, encoding="utf-8") as f:
            json.load(f)
        return True
    except (OSError, json.JSONDecodeError):
        return False


def is_arc_profile(path: Path) -> bool:
    return is_json_file(path / "StorableSidebar.json")


def discover_arc_profiles() -> list[Path]:
    profiles = []
    seen = set()
    for candidate in _arc_candidate_roots():
        resolved = candidate.expanduser()
        if resolved in seen:
            continue
        seen.add(resolved)
        if resolved.is_dir() and is_arc_profile(resolved):
            profiles.append(resolved)
    return profiles


def resolve_arc_profile(path: str | Path | None = None) -> Path:
    raw_path = path or os.environ.get("ARC_PROFILE_PATH") or default_arc_profile_path()
    profile = Path(raw_path).expanduser()
    if not profile.is_dir():
        raise FileNotFoundError(f"Arc profile path does not exist: {profile}")

    sidebar = profile / "StorableSidebar.json"
    if not is_json_file(sidebar):
        raise FileNotFoundError(f"Arc profile is missing a valid StorableSidebar.json: {sidebar}")

    return profile


def arc_json_path(name: str, profile: str | Path | None = None) -> Path:
    return resolve_arc_profile(profile) / name


def arc_favicons_path(profile: str | Path | None = None) -> Path:
    paths = arc_favicons_paths(profile)
    if paths:
        return paths[0]
    return resolve_arc_profile(profile) / "User Data" / "Default" / "Favicons"


def arc_favicons_paths(profile: str | Path | None = None) -> list[Path]:
    root = resolve_arc_profile(profile)
    user_data = root / "User Data"
    candidates = [user_data / "Default" / "Favicons"]
    candidates.extend(sorted(user_data.glob("Profile */Favicons")))
    return [path for path in candidates if is_sqlite_database(path)]


def default_zen_root() -> Path:
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "zen"
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA")
        return Path(appdata) / "zen" if appdata else Path.home() / "AppData" / "Roaming" / "zen"
    return Path.home() / ".zen"


def _candidate_zen_roots() -> Iterable[Path]:
    if sys.platform == "darwin":
        yield Path.home() / "Library" / "Application Support" / "zen"
    elif sys.platform == "win32":
        appdata = os.environ.get("APPDATA")
        yield Path(appdata) / "zen" if appdata else Path.home() / "AppData" / "Roaming" / "zen"
    else:
        yield Path.home() / ".zen"

    if sys.platform.startswith("linux"):
        yield Path.home() / ".var" / "app" / "app.zen_browser.zen" / "zen"
        yield Path.home() / ".var" / "app" / "app.zen_browser.zen" / "config" / "zen"
        yield Path.home() / ".var" / "app" / "app.zen_browser.zen" / ".zen"


def _profile_from_ini(zen_root: Path) -> Optional[Path]:
    installs_ini = zen_root / "installs.ini"
    if installs_ini.exists():
        config = configparser.ConfigParser()
        config.read(installs_ini)
        for section in config.sections():
            default = config.get(section, "Default", fallback=None)
            if default:
                profile = zen_root / default if not Path(default).is_absolute() else Path(default)
                if profile.is_dir():
                    return profile

    profiles_ini = zen_root / "profiles.ini"
    if profiles_ini.exists():
        config = configparser.ConfigParser()
        config.read(profiles_ini)
        for section in config.sections():
            if not section.startswith("Profile"):
                continue
            if config.get(section, "Default", fallback="0") != "1":
                continue

            profile_path = config.get(section, "Path", fallback=None)
            if not profile_path:
                continue

            is_relative = config.get(section, "IsRelative", fallback="1") == "1"
            profile = zen_root / profile_path if is_relative else Path(profile_path)
            if profile.is_dir():
                return profile

    return None


def _profiles_from_ini(zen_root: Path) -> list[Path]:
    profiles = []
    profiles_ini = zen_root / "profiles.ini"
    if not profiles_ini.exists():
        return profiles

    config = configparser.ConfigParser()
    config.read(profiles_ini)
    for section in config.sections():
        if not section.startswith("Profile"):
            continue
        profile_path = config.get(section, "Path", fallback=None)
        if not profile_path:
            continue
        is_relative = config.get(section, "IsRelative", fallback="1") == "1"
        profile = zen_root / profile_path if is_relative else Path(profile_path)
        if profile.is_dir():
            profiles.append(profile)

    return profiles


def is_zen_profile(path: Path) -> bool:
    return path.is_dir() and (path / "zen-sessions.jsonlz4").exists()


def zen_profiles_in_root(zen_root: Path) -> list[Path]:
    profiles = []
    if is_zen_profile(zen_root):
        profiles.append(zen_root)

    profiles.extend(profile for profile in _profiles_from_ini(zen_root) if is_zen_profile(profile))

    profiles_dir = zen_root / "Profiles"
    if profiles_dir.is_dir():
        profiles.extend(profile for profile in sorted(profiles_dir.iterdir()) if is_zen_profile(profile))

    deduped = []
    seen = set()
    for profile in profiles:
        try:
            key = profile.resolve()
        except OSError:
            key = profile
        if key in seen:
            continue
        seen.add(key)
        deduped.append(profile)
    return deduped


def discover_zen_profiles() -> list[Path]:
    profiles = []
    for zen_root in _candidate_zen_roots():
        if zen_root.exists():
            profiles.extend(zen_profiles_in_root(zen_root))
    return profiles


def resolve_zen_profile(path: str | Path | None = None, name: str | None = None) -> Path:
    requested_path = path or os.environ.get("ZEN_PROFILE_PATH")
    if requested_path:
        candidate = Path(requested_path).expanduser()
        if not candidate.is_dir():
            raise FileNotFoundError(f"ZEN_PROFILE_PATH does not exist: {candidate}")
        if is_zen_profile(candidate):
            return candidate
        default_profile = _profile_from_ini(candidate)
        if default_profile and is_zen_profile(default_profile):
            return default_profile
        profiles = zen_profiles_in_root(candidate)
        if profiles:
            return profiles[0]
        raise FileNotFoundError(f"Zen path does not contain a profile with zen-sessions.jsonlz4: {candidate}")

    requested_name = name or os.environ.get("ZEN_PROFILE_NAME")
    if requested_name:
        for zen_root in _candidate_zen_roots():
            profiles_dir = zen_root / "Profiles"
            if not profiles_dir.is_dir():
                continue
            for profile in profiles_dir.iterdir():
                if requested_name in profile.name and is_zen_profile(profile):
                    return profile
        raise FileNotFoundError(f"ZEN_PROFILE_NAME not found: {requested_name}")

    for zen_root in _candidate_zen_roots():
        if not zen_root.exists():
            continue

        profile = _profile_from_ini(zen_root)
        if profile and is_zen_profile(profile):
            return profile

        profiles = zen_profiles_in_root(zen_root)
        if profiles:
            return profiles[0]

    raise FileNotFoundError("No Zen profile with zen-sessions.jsonlz4 found")


def zen_session_files(profile: str | Path) -> list[Path]:
    profile_path = Path(profile).expanduser()
    return [
        profile_path / "zen-sessions.jsonlz4",
        profile_path / "sessionstore.jsonlz4",
        profile_path / "sessionstore-backups" / "recovery.jsonlz4",
    ]
