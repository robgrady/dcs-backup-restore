"""UUID detection and remapping for DCS input devices.

DCS stores input bindings as files named:
    Config/Input/<module>/<input_type>/<Device Name> {<UUID>}.diff.lua

When a device is plugged into a different USB port or a new system, the UUID
changes and DCS can't find the old bindings. This module handles:
1. Extracting device name + UUID from filenames
2. Detecting current devices from the DCS log file
3. Remapping old UUIDs to new ones in filenames and file contents
"""

import os
import re
from pathlib import Path

from .models import DeviceInfo, UUIDMapping


# Pattern matching DCS input filenames: "Device Name {UUID}.diff.lua"
INPUT_FILENAME_RE = re.compile(r"^(.+?)\s*\{([0-9A-Fa-f-]+)\}\.diff\.lua$")

# Pattern matching device entries in dcs.log
# Example: DInput: Found device "Thrustmaster Warthog Throttle" {B05B0C50-...}
LOG_DEVICE_RE = re.compile(
    r'DInput:\s+Found\s+device\s+"([^"]+)"\s*\{([0-9A-Fa-f-]+)\}'
)

# Pattern matching UUIDs inside .diff.lua file contents (used in modifier refs)
UUID_IN_CONTENT_RE = re.compile(r"\{([0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12})\}")


def parse_input_filename(filename: str) -> tuple[str, str] | None:
    """Extract (device_name, uuid) from a DCS input filename.

    Returns None if the filename doesn't match the expected pattern.
    """
    m = INPUT_FILENAME_RE.match(filename)
    if m:
        return m.group(1).strip(), m.group(2)
    return None


def extract_devices_from_input_dir(input_dir: Path) -> list[DeviceInfo]:
    """Scan Config/Input/ and extract unique (device_name, uuid) pairs."""
    devices: dict[tuple[str, str], DeviceInfo] = {}

    for root, _dirs, files in os.walk(input_dir):
        for fname in files:
            parsed = parse_input_filename(fname)
            if parsed:
                name, uuid = parsed
                key = (name, uuid)
                if key not in devices:
                    devices[key] = DeviceInfo(name=name, uuid=uuid)

    return sorted(devices.values(), key=lambda d: (d.name, d.uuid))


def detect_devices_from_log(dcs_path: Path) -> list[DeviceInfo]:
    """Parse dcs.log to find currently detected devices and their UUIDs.

    DCS must have been run at least once for this log to exist.
    """
    log_path = dcs_path / "Logs" / "dcs.log"
    if not log_path.is_file():
        # Try alternate location
        log_path = dcs_path / "dcs.log"
        if not log_path.is_file():
            return []

    devices: dict[tuple[str, str], DeviceInfo] = {}
    try:
        text = log_path.read_text(encoding="utf-8", errors="replace")
        for m in LOG_DEVICE_RE.finditer(text):
            name = m.group(1).strip()
            uuid = m.group(2)
            key = (name, uuid)
            if key not in devices:
                devices[key] = DeviceInfo(name=name, uuid=uuid)
    except OSError:
        return []

    return sorted(devices.values(), key=lambda d: (d.name, d.uuid))


def auto_match_devices(
    backup_devices: list[DeviceInfo],
    current_devices: list[DeviceInfo],
) -> list[UUIDMapping]:
    """Automatically match backup devices to current devices by name.

    For each backup device, if a current device exists with the same name,
    create a mapping. If the UUID already matches, skip it (no remap needed).
    """
    # Build lookup: device_name -> list of current UUIDs
    current_by_name: dict[str, list[str]] = {}
    for dev in current_devices:
        current_by_name.setdefault(dev.name, []).append(dev.uuid)

    mappings: list[UUIDMapping] = []
    for dev in backup_devices:
        current_uuids = current_by_name.get(dev.name, [])
        if not current_uuids:
            continue
        # If exact UUID exists, no remap needed
        if dev.uuid in current_uuids:
            continue
        # Use the first matching device by name
        mappings.append(UUIDMapping(
            device_name=dev.name,
            old_uuid=dev.uuid,
            new_uuid=current_uuids[0],
        ))

    return mappings


def remap_filename(filename: str, mappings: list[UUIDMapping]) -> str:
    """Rename a .diff.lua filename by replacing old UUID with new UUID."""
    for mapping in mappings:
        old_pattern = f"{{{mapping.old_uuid}}}"
        new_pattern = f"{{{mapping.new_uuid}}}"
        if old_pattern in filename:
            return filename.replace(old_pattern, new_pattern)
    return filename


def remap_file_contents(contents: str, mappings: list[UUIDMapping]) -> str:
    """Replace old UUIDs with new UUIDs inside .diff.lua file contents.

    Modifier key bindings reference other devices by UUID, so we need
    to update those references too.
    """
    result = contents
    for mapping in mappings:
        result = result.replace(mapping.old_uuid, mapping.new_uuid)
    return result
