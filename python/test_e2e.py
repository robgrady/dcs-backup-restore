"""End-to-end test: create mock DCS folder, backup, remap UUIDs, restore."""

import json
import os
import shutil
import tempfile
import zipfile
from pathlib import Path

# Adjust path so we can import src
import sys
sys.path.insert(0, str(Path(__file__).parent))

from src.models import BackupCategory, BackupManifest, DeviceInfo, UUIDMapping
from src.backup import create_backup, read_manifest_from_zip, collect_files
from src.restore import restore_backup
from src.uuid_remapper import (
    parse_input_filename,
    extract_devices_from_input_dir,
    detect_devices_from_log,
    auto_match_devices,
    remap_filename,
    remap_file_contents,
)
from src.dcs_paths import validate_dcs_path


OLD_UUID_THROTTLE = "B05B0C50-1111-2222-3333-444444444444"
OLD_UUID_STICK = "A01A0B40-5555-6666-7777-888888888888"
NEW_UUID_THROTTLE = "C06C0D60-AAAA-BBBB-CCCC-DDDDDDDDDDDD"
NEW_UUID_STICK = "D07D0E70-EEEE-FFFF-0000-111111111111"


def create_mock_dcs(base: Path) -> Path:
    """Create a realistic mock DCS Saved Games folder."""
    dcs = base / "DCS"

    # Config/options.lua
    opts = dcs / "Config" / "options.lua"
    opts.parent.mkdir(parents=True)
    opts.write_text(
        'options = {\n'
        '    ["graphics"] = {\n'
        '        ["fullScreen"] = false,\n'
        '        ["width"] = 1920,\n'
        '    },\n'
        '    ["sound"] = {\n'
        '        ["volume"] = 80,\n'
        '    },\n'
        '}\n'
    )

    # Config/autoexec.cfg
    (dcs / "Config" / "autoexec.cfg").write_text(
        'options.graphics.maxfps = 120\n'
    )

    # Config/serverSettings.lua
    (dcs / "Config" / "serverSettings.lua").write_text(
        'cfg = { ["name"] = "My Server" }\n'
    )

    # Config/missionEditor.lua
    (dcs / "Config" / "missionEditor.lua").write_text(
        'missionEditor = { ["recent"] = {} }\n'
    )

    # Config/MonitorSetup/
    mon_dir = dcs / "Config" / "MonitorSetup"
    mon_dir.mkdir(parents=True)
    (mon_dir / "monitor_config.lua").write_text(
        '_ = { ["name"] = "single" }\n'
    )

    # Config/View/ (snapviews)
    view_dir = dcs / "Config" / "View"
    view_dir.mkdir(parents=True)
    (view_dir / "SnapViews.lua").write_text(
        'SnapViews = {}\n'
    )

    # Kneeboard/
    knee_dir = dcs / "Kneeboard" / "FA-18C_hornet"
    knee_dir.mkdir(parents=True)
    (knee_dir / "checklist.png").write_bytes(b"FAKEPNG")

    # Config/Input/ — input bindings with device UUIDs
    # FA-18C throttle
    inp_hornet_js = dcs / "Config" / "Input" / "FA-18C_hornet" / "joystick"
    inp_hornet_js.mkdir(parents=True)
    throttle_file = inp_hornet_js / f"Thrustmaster TWCS Throttle {{{OLD_UUID_THROTTLE}}}.diff.lua"
    throttle_file.write_text(
        'local diff = {\n'
        '    ["keyDiffs"] = {\n'
        '        ["d1001pnilu1001cd15vd1"] = {\n'
        '            ["added"] = {\n'
        '                [1] = { ["key"] = "JOY_BTN1" },\n'
        '            },\n'
        '            ["name"] = "Throttle Axis",\n'
        '        },\n'
        '    },\n'
        '}\n'
        'return diff\n'
    )

    # FA-18C stick with modifier referencing throttle UUID
    stick_file = inp_hornet_js / f"VKB Gladiator {{{OLD_UUID_STICK}}}.diff.lua"
    stick_file.write_text(
        'local diff = {\n'
        '    ["keyDiffs"] = {\n'
        '        ["d2002pnilu2002cd20vd1"] = {\n'
        '            ["added"] = {\n'
        '                [1] = {\n'
        '                    ["key"] = "JOY_BTN2",\n'
        f'                    ["reformers"] = {{ ["Thrustmaster TWCS Throttle"] = "{OLD_UUID_THROTTLE}" }},\n'
        '                },\n'
        '            },\n'
        '            ["name"] = "Weapon Release",\n'
        '        },\n'
        '    },\n'
        '}\n'
        'return diff\n'
    )

    # A-10C stick (same devices, different module)
    inp_a10 = dcs / "Config" / "Input" / "A-10C" / "joystick"
    inp_a10.mkdir(parents=True)
    (inp_a10 / f"VKB Gladiator {{{OLD_UUID_STICK}}}.diff.lua").write_text(
        'local diff = { ["keyDiffs"] = {} }\nreturn diff\n'
    )

    # Fake DCS log with "new" device UUIDs (simulating USB port change)
    log_dir = dcs / "Logs"
    log_dir.mkdir()
    (log_dir / "dcs.log").write_text(
        'INFO: DCS/2.9.4.55243\n'
        f'DInput: Found device "Thrustmaster TWCS Throttle" {{{NEW_UUID_THROTTLE}}}\n'
        f'DInput: Found device "VKB Gladiator" {{{NEW_UUID_STICK}}}\n'
        'DInput: Found device "Keyboard" {00000000-0000-0000-0000-000000000000}\n'
    )

    return dcs


def test_parse_input_filename():
    print("  test_parse_input_filename...", end=" ")
    result = parse_input_filename(f"Thrustmaster TWCS Throttle {{{OLD_UUID_THROTTLE}}}.diff.lua")
    assert result is not None
    assert result[0] == "Thrustmaster TWCS Throttle"
    assert result[1] == OLD_UUID_THROTTLE

    assert parse_input_filename("not_a_device.diff.lua") is None
    assert parse_input_filename("readme.txt") is None
    print("OK")


def test_extract_devices(dcs_path: Path):
    print("  test_extract_devices...", end=" ")
    input_dir = dcs_path / "Config" / "Input"
    devices = extract_devices_from_input_dir(input_dir)
    names = {d.name for d in devices}
    assert "Thrustmaster TWCS Throttle" in names
    assert "VKB Gladiator" in names
    assert len(devices) == 2  # Two unique (name, uuid) pairs
    print(f"OK (found {len(devices)} devices)")


def test_detect_from_log(dcs_path: Path):
    print("  test_detect_from_log...", end=" ")
    devices = detect_devices_from_log(dcs_path)
    uuids = {d.uuid for d in devices}
    assert NEW_UUID_THROTTLE in uuids
    assert NEW_UUID_STICK in uuids
    # Keyboard should also be detected
    assert len(devices) == 3
    print(f"OK (found {len(devices)} devices)")


def test_auto_match():
    print("  test_auto_match...", end=" ")
    backup_devs = [
        DeviceInfo("Thrustmaster TWCS Throttle", OLD_UUID_THROTTLE),
        DeviceInfo("VKB Gladiator", OLD_UUID_STICK),
    ]
    current_devs = [
        DeviceInfo("Thrustmaster TWCS Throttle", NEW_UUID_THROTTLE),
        DeviceInfo("VKB Gladiator", NEW_UUID_STICK),
        DeviceInfo("Keyboard", "00000000-0000-0000-0000-000000000000"),
    ]
    mappings = auto_match_devices(backup_devs, current_devs)
    assert len(mappings) == 2
    m_map = {m.device_name: m for m in mappings}
    assert m_map["Thrustmaster TWCS Throttle"].new_uuid == NEW_UUID_THROTTLE
    assert m_map["VKB Gladiator"].new_uuid == NEW_UUID_STICK
    print(f"OK ({len(mappings)} mappings)")


def test_remap_filename():
    print("  test_remap_filename...", end=" ")
    mappings = [UUIDMapping("Throttle", OLD_UUID_THROTTLE, NEW_UUID_THROTTLE)]
    old_name = f"Thrustmaster TWCS Throttle {{{OLD_UUID_THROTTLE}}}.diff.lua"
    new_name = remap_filename(old_name, mappings)
    assert NEW_UUID_THROTTLE in new_name
    assert OLD_UUID_THROTTLE not in new_name
    print("OK")


def test_remap_contents():
    print("  test_remap_contents...", end=" ")
    mappings = [UUIDMapping("Throttle", OLD_UUID_THROTTLE, NEW_UUID_THROTTLE)]
    content = f'["reformers"] = {{ ["Throttle"] = "{OLD_UUID_THROTTLE}" }}'
    result = remap_file_contents(content, mappings)
    assert NEW_UUID_THROTTLE in result
    assert OLD_UUID_THROTTLE not in result
    print("OK")


def test_validate_dcs_path(dcs_path: Path, base: Path):
    print("  test_validate_dcs_path...", end=" ")
    assert validate_dcs_path(dcs_path) is True
    assert validate_dcs_path(base / "nonexistent") is False
    assert validate_dcs_path(base) is False  # base has no Config/
    print("OK")


def test_backup_and_restore(dcs_path: Path, tmp: Path):
    print("  test_backup_and_restore...", end=" ")

    dest_dir = tmp / "backups"
    dest_dir.mkdir()

    # Create backup with all categories
    all_cats = list(BackupCategory)
    zip_path = create_backup(dcs_path, dest_dir, all_cats)
    assert zip_path.is_file()
    assert zip_path.suffix == ".zip"

    # Read manifest
    manifest = read_manifest_from_zip(zip_path)
    assert manifest.timestamp
    assert len(manifest.files) > 0
    assert len(manifest.devices) == 2

    # Verify ZIP contents
    with zipfile.ZipFile(zip_path, "r") as zf:
        names = zf.namelist()
        assert "manifest.json" in names
        assert "Config/options.lua" in names
        # Check an input file is present
        input_files = [n for n in names if "Input" in n and ".diff.lua" in n]
        assert len(input_files) >= 2

    print(f"OK (ZIP has {len(names)} entries)")
    return zip_path, manifest


def test_restore_with_remap(zip_path: Path, tmp: Path):
    print("  test_restore_with_remap...", end=" ")

    # Create a fresh DCS folder to restore into
    restore_dcs = tmp / "DCS_restored"
    (restore_dcs / "Config").mkdir(parents=True)
    # Add a log with new UUIDs
    (restore_dcs / "Logs").mkdir()
    (restore_dcs / "Logs" / "dcs.log").write_text(
        f'DInput: Found device "Thrustmaster TWCS Throttle" {{{NEW_UUID_THROTTLE}}}\n'
        f'DInput: Found device "VKB Gladiator" {{{NEW_UUID_STICK}}}\n'
    )

    # Build UUID mappings
    mappings = [
        UUIDMapping("Thrustmaster TWCS Throttle", OLD_UUID_THROTTLE, NEW_UUID_THROTTLE),
        UUIDMapping("VKB Gladiator", OLD_UUID_STICK, NEW_UUID_STICK),
    ]

    # Restore
    safety = restore_backup(
        zip_path, restore_dcs, list(BackupCategory),
        uuid_mappings=mappings,
        do_safety_backup=True,
    )

    # Verify settings restored
    opts = restore_dcs / "Config" / "options.lua"
    assert opts.is_file()
    assert "fullScreen" in opts.read_text()

    # Verify input files have NEW UUIDs in filenames
    hornet_js = restore_dcs / "Config" / "Input" / "FA-18C_hornet" / "joystick"
    input_files = list(hornet_js.glob("*.diff.lua"))
    input_names = [f.name for f in input_files]

    found_new_throttle = any(NEW_UUID_THROTTLE in n for n in input_names)
    found_new_stick = any(NEW_UUID_STICK in n for n in input_names)
    found_old_throttle = any(OLD_UUID_THROTTLE in n for n in input_names)
    found_old_stick = any(OLD_UUID_STICK in n for n in input_names)

    assert found_new_throttle, f"New throttle UUID not in filenames: {input_names}"
    assert found_new_stick, f"New stick UUID not in filenames: {input_names}"
    assert not found_old_throttle, f"Old throttle UUID still in filenames: {input_names}"
    assert not found_old_stick, f"Old stick UUID still in filenames: {input_names}"

    # Verify modifier UUID inside stick file was also remapped
    stick_files = [f for f in input_files if "VKB" in f.name]
    assert len(stick_files) == 1
    stick_content = stick_files[0].read_text()
    assert NEW_UUID_THROTTLE in stick_content, "Modifier UUID not remapped inside file"
    assert OLD_UUID_THROTTLE not in stick_content, "Old modifier UUID still in file"

    # Verify safety backup was created
    assert safety is not None
    assert safety.is_dir()

    # Verify kneeboard restored
    knee = restore_dcs / "Kneeboard" / "FA-18C_hornet" / "checklist.png"
    assert knee.is_file()

    print("OK (filenames + contents remapped, safety backup created)")


def main():
    print("=" * 60)
    print("DCS Backup & Restore - End-to-End Tests")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as tmp_str:
        tmp = Path(tmp_str)
        dcs_path = create_mock_dcs(tmp)

        print("\n[Unit Tests]")
        test_parse_input_filename()
        test_extract_devices(dcs_path)
        test_detect_from_log(dcs_path)
        test_auto_match()
        test_remap_filename()
        test_remap_contents()
        test_validate_dcs_path(dcs_path, tmp)

        print("\n[Integration Tests]")
        zip_path, manifest = test_backup_and_restore(dcs_path, tmp)
        test_restore_with_remap(zip_path, tmp)

    print("\n" + "=" * 60)
    print("ALL TESTS PASSED")
    print("=" * 60)


if __name__ == "__main__":
    main()
