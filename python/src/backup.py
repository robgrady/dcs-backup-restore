"""Backup engine - collects DCS files and creates ZIP archives."""

import os
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Callable

from .dcs_paths import get_dcs_version
from .models import (
    BackupCategory,
    BackupManifest,
    CATEGORY_PATHS,
    DeviceInfo,
)
from .uuid_remapper import extract_devices_from_input_dir


def collect_files(
    dcs_path: Path,
    categories: list[BackupCategory],
) -> list[str]:
    """Collect all files to back up, returned as relative paths from dcs_path."""
    files: list[str] = []

    for category in categories:
        for rel_path_str in CATEGORY_PATHS[category]:
            full_path = dcs_path / rel_path_str

            if full_path.is_file():
                files.append(rel_path_str)
            elif full_path.is_dir():
                for root, _dirs, filenames in os.walk(full_path):
                    for fname in filenames:
                        abs_path = Path(root) / fname
                        rel = abs_path.relative_to(dcs_path)
                        files.append(str(rel))

    return sorted(set(files))


def create_backup(
    dcs_path: Path,
    dest_dir: Path,
    categories: list[BackupCategory],
    progress_callback: Callable[[int, int, str], None] | None = None,
) -> Path:
    """Create a backup ZIP archive.

    Args:
        dcs_path: The DCS Saved Games folder.
        dest_dir: Directory to write the ZIP into.
        categories: Which categories to include.
        progress_callback: Optional (current, total, filename) callback.

    Returns:
        Path to the created ZIP file.
    """
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    zip_name = f"DCS_Backup_{timestamp}.zip"
    zip_path = dest_dir / zip_name

    files = collect_files(dcs_path, categories)
    total = len(files) + 1  # +1 for the manifest

    # Extract device info if inputs are included
    devices: list[DeviceInfo] = []
    if BackupCategory.INPUTS in categories:
        input_dir = dcs_path / "Config" / "Input"
        if input_dir.is_dir():
            devices = extract_devices_from_input_dir(input_dir)

    dcs_version = get_dcs_version(dcs_path)

    manifest = BackupManifest.create(
        dcs_path=str(dcs_path),
        dcs_version=dcs_version,
        categories=categories,
        files=files,
        devices=devices,
    )

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for i, rel_path in enumerate(files):
            full_path = dcs_path / rel_path
            if full_path.is_file():
                zf.write(full_path, rel_path)
                if progress_callback:
                    progress_callback(i + 1, total, rel_path)

        # Write manifest as the last entry
        zf.writestr("manifest.json", manifest.to_json())
        if progress_callback:
            progress_callback(total, total, "manifest.json")

    return zip_path


def read_manifest_from_zip(zip_path: Path) -> BackupManifest:
    """Read and parse the manifest from a backup ZIP."""
    with zipfile.ZipFile(zip_path, "r") as zf:
        manifest_text = zf.read("manifest.json").decode("utf-8")
    return BackupManifest.from_json(manifest_text)
