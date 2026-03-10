"""Auto-detect and validate DCS World Saved Games folder paths."""

import os
from pathlib import Path


# Known DCS Saved Games folder names (standalone)
DCS_FOLDER_NAMES = [
    "DCS",
    "DCS.openbeta",
]


def get_saved_games_dir() -> Path:
    """Return the Windows Saved Games directory."""
    user_profile = os.environ.get("USERPROFILE", "")
    if user_profile:
        return Path(user_profile) / "Saved Games"
    return Path.home() / "Saved Games"


def detect_dcs_paths() -> list[Path]:
    """Find all DCS Saved Games folders that exist on this system.

    Returns a list of valid DCS paths, sorted with 'DCS' (stable) first.
    """
    saved_games = get_saved_games_dir()
    found = []
    for name in DCS_FOLDER_NAMES:
        candidate = saved_games / name
        if candidate.is_dir() and validate_dcs_path(candidate):
            found.append(candidate)
    return found


def validate_dcs_path(path: Path) -> bool:
    """Check that a folder looks like a real DCS Saved Games directory.

    We look for the Config/ subdirectory as a minimum indicator.
    """
    if not path.is_dir():
        return False
    config_dir = path / "Config"
    return config_dir.is_dir()


def get_dcs_version(dcs_path: Path) -> str | None:
    """Try to read the DCS version from autoupdate.cfg or similar files."""
    autoupdate = dcs_path / "autoupdate.cfg"
    if autoupdate.is_file():
        try:
            text = autoupdate.read_text(encoding="utf-8")
            # autoupdate.cfg is a simple Lua-style file with version info
            for line in text.splitlines():
                if '"version"' in line or "'version'" in line:
                    # Extract the value between quotes
                    parts = line.split('"')
                    if len(parts) >= 4:
                        return parts[3]
        except OSError:
            pass
    return None
