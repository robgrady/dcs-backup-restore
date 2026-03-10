use std::path::Path;

use crate::backup::{create_backup, read_manifest_from_zip};
use crate::dcs_paths::{detect_dcs_paths, validate_dcs_path};
use crate::models::{BackupCategory, BackupManifest, CategoryInfo, DeviceInfo, UUIDMapping};
use crate::restore::restore_backup;
use crate::uuid_remapper::{auto_match_devices, detect_devices_from_log};

/// Detect DCS Saved Games folders on this system.
#[tauri::command]
pub fn cmd_detect_dcs_paths() -> Vec<String> {
    detect_dcs_paths()
        .into_iter()
        .map(|p| p.to_string_lossy().to_string())
        .collect()
}

/// Validate a path as a DCS Saved Games folder.
#[tauri::command]
pub fn cmd_validate_dcs_path(path: String) -> bool {
    validate_dcs_path(Path::new(&path))
}

/// Get all backup category options with labels.
#[tauri::command]
pub fn cmd_get_categories() -> Vec<CategoryInfo> {
    BackupCategory::all()
        .into_iter()
        .map(|c| {
            let id = serde_json::to_value(&c).unwrap().as_str().unwrap().to_string();
            CategoryInfo { id, label: c.label().to_string() }
        })
        .collect()
}

/// Create a backup ZIP archive.
#[tauri::command]
pub fn cmd_create_backup(
    dcs_path: String,
    dest_dir: String,
    categories: Vec<BackupCategory>,
) -> Result<BackupResult, String> {
    let (zip_path, file_count) = create_backup(
        Path::new(&dcs_path),
        Path::new(&dest_dir),
        &categories,
    )?;
    Ok(BackupResult { zip_path, file_count })
}

#[derive(serde::Serialize)]
pub struct BackupResult {
    pub zip_path: String,
    pub file_count: usize,
}

/// Read the manifest from a backup ZIP file.
#[tauri::command]
pub fn cmd_read_manifest(zip_path: String) -> Result<BackupManifest, String> {
    read_manifest_from_zip(Path::new(&zip_path))
}

/// Detect devices from DCS log file (current system state).
#[tauri::command]
pub fn cmd_detect_current_devices(dcs_path: String) -> Vec<DeviceInfo> {
    detect_devices_from_log(Path::new(&dcs_path))
}

/// Auto-match backup devices to current devices by name.
#[tauri::command]
pub fn cmd_auto_match_devices(
    backup_devices: Vec<DeviceInfo>,
    current_devices: Vec<DeviceInfo>,
) -> Vec<UUIDMapping> {
    auto_match_devices(&backup_devices, &current_devices)
}

/// Restore from a backup ZIP with UUID remapping.
#[tauri::command]
pub fn cmd_restore_backup(
    zip_path: String,
    dcs_path: String,
    categories: Vec<BackupCategory>,
    uuid_mappings: Vec<UUIDMapping>,
    do_safety_backup: bool,
) -> Result<RestoreResult, String> {
    let (restored_count, safety_path) = restore_backup(
        Path::new(&zip_path),
        Path::new(&dcs_path),
        &categories,
        &uuid_mappings,
        do_safety_backup,
    )?;
    Ok(RestoreResult { restored_count, safety_path })
}

#[derive(serde::Serialize)]
pub struct RestoreResult {
    pub restored_count: usize,
    pub safety_path: Option<String>,
}
