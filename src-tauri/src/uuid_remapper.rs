use regex::Regex;
use std::collections::{HashMap, HashSet};
use std::path::Path;
use walkdir::WalkDir;

use crate::models::{DeviceInfo, UUIDMapping};

/// Parse device name and UUID from a DCS input filename.
/// Pattern: "Device Name {UUID}.diff.lua"
pub fn parse_input_filename(filename: &str) -> Option<(String, String)> {
    let re = Regex::new(r"^(.+?)\s*\{([0-9A-Fa-f-]+)\}\.diff\.lua$").unwrap();
    re.captures(filename).map(|caps| {
        (caps[1].trim().to_string(), caps[2].to_string())
    })
}

/// Scan Config/Input/ and extract unique (device_name, uuid) pairs.
pub fn extract_devices_from_input_dir(input_dir: &Path) -> Vec<DeviceInfo> {
    let mut seen = HashSet::new();
    let mut devices = Vec::new();

    for entry in WalkDir::new(input_dir).into_iter().filter_map(|e| e.ok()) {
        if let Some(fname) = entry.file_name().to_str() {
            if let Some((name, uuid)) = parse_input_filename(fname) {
                let key = (name.clone(), uuid.clone());
                if seen.insert(key) {
                    devices.push(DeviceInfo { name, uuid });
                }
            }
        }
    }

    devices.sort_by(|a, b| (&a.name, &a.uuid).cmp(&(&b.name, &b.uuid)));
    devices
}

/// Parse dcs.log to find currently detected devices and their UUIDs.
pub fn detect_devices_from_log(dcs_path: &Path) -> Vec<DeviceInfo> {
    let log_path = dcs_path.join("Logs").join("dcs.log");
    let log_path = if log_path.is_file() {
        log_path
    } else {
        let alt = dcs_path.join("dcs.log");
        if alt.is_file() { alt } else { return vec![]; }
    };

    let text = match std::fs::read_to_string(&log_path) {
        Ok(t) => t,
        Err(_) => return vec![],
    };

    let re = Regex::new(r#"DInput:\s+Found\s+device\s+"([^"]+)"\s*\{([0-9A-Fa-f-]+)\}"#).unwrap();
    let mut seen = HashSet::new();
    let mut devices = Vec::new();

    for caps in re.captures_iter(&text) {
        let name = caps[1].trim().to_string();
        let uuid = caps[2].to_string();
        let key = (name.clone(), uuid.clone());
        if seen.insert(key) {
            devices.push(DeviceInfo { name, uuid });
        }
    }

    devices.sort_by(|a, b| (&a.name, &a.uuid).cmp(&(&b.name, &b.uuid)));
    devices
}

/// Automatically match backup devices to current devices by name.
pub fn auto_match_devices(
    backup_devices: &[DeviceInfo],
    current_devices: &[DeviceInfo],
) -> Vec<UUIDMapping> {
    let mut current_by_name: HashMap<&str, Vec<&str>> = HashMap::new();
    for dev in current_devices {
        current_by_name.entry(&dev.name).or_default().push(&dev.uuid);
    }

    let mut mappings = Vec::new();
    for dev in backup_devices {
        if let Some(current_uuids) = current_by_name.get(dev.name.as_str()) {
            if current_uuids.contains(&dev.uuid.as_str()) {
                continue; // UUID already matches, no remap needed
            }
            mappings.push(UUIDMapping {
                device_name: dev.name.clone(),
                old_uuid: dev.uuid.clone(),
                new_uuid: current_uuids[0].to_string(),
            });
        }
    }

    mappings
}

/// Rename a .diff.lua filename by replacing old UUID with new UUID.
pub fn remap_filename(filename: &str, mappings: &[UUIDMapping]) -> String {
    let mut result = filename.to_string();
    for m in mappings {
        let old = format!("{{{}}}", m.old_uuid);
        let new = format!("{{{}}}", m.new_uuid);
        result = result.replace(&old, &new);
    }
    result
}

/// Replace old UUIDs with new UUIDs inside .diff.lua file contents.
pub fn remap_file_contents(contents: &str, mappings: &[UUIDMapping]) -> String {
    let mut result = contents.to_string();
    for m in mappings {
        result = result.replace(&m.old_uuid, &m.new_uuid);
    }
    result
}
