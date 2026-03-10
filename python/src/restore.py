"""Restore engine - extracts backup ZIPs with optional UUID remapping."""

import os
import shutil
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Callable

from .models import BackupCategory, BackupManifest, CATEGORY_PATHS, UUIDMapping
from .uuid_remapper import remap_file_contents, remap_filename


def _category_for_file(rel_path: str) -> BackupCategory | None:
    """Determine which backup category a file belongs to."""
    normalized = rel_path.replace("\\", "/")
    for category, paths in CATEGORY_PATHS.items():
        for cat_path in paths:
            if normalized == cat_path or normalized.startswith(cat_path + "/"):
                return category
    return None


def create_safety_backup(dcs_path: Path) -> Path:
    """Create a quick safety backup of current files before overwriting.

    Returns the path to the safety backup directory.
    """
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    safety_dir = dcs_path / "_safety_backup" / timestamp

    config_dir = dcs_path / "Config"
    if config_dir.is_dir():
        dest = safety_dir / "Config"
        shutil.copytree(config_dir, dest, dirs_exist_ok=True)

    kneeboard_dir = dcs_path / "Kneeboard"
    if kneeboard_dir.is_dir():
        dest = safety_dir / "Kneeboard"
        shutil.copytree(kneeboard_dir, dest, dirs_exist_ok=True)

    return safety_dir


def restore_backup(
    zip_path: Path,
    dcs_path: Path,
    categories: list[BackupCategory],
    uuid_mappings: list[UUIDMapping] | None = None,
    do_safety_backup: bool = True,
    progress_callback: Callable[[int, int, str], None] | None = None,
) -> Path | None:
    """Restore files from a backup ZIP into the DCS Saved Games folder.

    Args:
        zip_path: Path to the backup ZIP.
        dcs_path: The DCS Saved Games folder to restore into.
        categories: Which categories to restore.
        uuid_mappings: Optional UUID remappings for input files.
        do_safety_backup: If True, back up current files first.
        progress_callback: Optional (current, total, filename) callback.

    Returns:
        Path to the safety backup dir if one was created, else None.
    """
    if uuid_mappings is None:
        uuid_mappings = []

    # Build the set of category values to filter by
    selected = {c.value for c in categories}

    safety_path = None
    if do_safety_backup:
        safety_path = create_safety_backup(dcs_path)

    with zipfile.ZipFile(zip_path, "r") as zf:
        # Filter to just the files we want to restore
        entries = [
            name for name in zf.namelist()
            if name != "manifest.json" and _category_for_file(name) is not None
            and _category_for_file(name).value in selected
        ]

        total = len(entries)
        for i, rel_path in enumerate(entries):
            normalized = rel_path.replace("\\", "/")
            data = zf.read(rel_path)

            # Apply UUID remapping for input files
            is_input_file = normalized.startswith("Config/Input/") and normalized.endswith(".diff.lua")
            dest_rel = rel_path

            if is_input_file and uuid_mappings:
                # Remap the filename
                parts = normalized.rsplit("/", 1)
                if len(parts) == 2:
                    dir_part, fname = parts
                    new_fname = remap_filename(fname, uuid_mappings)
                    dest_rel = f"{dir_part}/{new_fname}"

                # Remap UUIDs inside file contents
                text = data.decode("utf-8", errors="replace")
                text = remap_file_contents(text, uuid_mappings)
                data = text.encode("utf-8")

            dest_path = dcs_path / dest_rel
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            dest_path.write_bytes(data)

            if progress_callback:
                progress_callback(i + 1, total, dest_rel)

    return safety_path
