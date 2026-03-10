use std::collections::BTreeSet;
use std::fs::File;
use std::io::{Read, Write};
use std::path::Path;
use walkdir::WalkDir;
use zip::write::SimpleFileOptions;
use zip::ZipWriter;

use crate::dcs_paths::get_dcs_version;
use crate::models::{BackupCategory, BackupManifest, APP_VERSION};
use crate::uuid_remapper::extract_devices_from_input_dir;

/// Collect all files to back up, returned as relative paths from dcs_path.
pub fn collect_files(dcs_path: &Path, categories: &[BackupCategory]) -> Vec<String> {
    let mut files = BTreeSet::new();

    for category in categories {
        for rel_path_str in category.paths() {
            let full_path = dcs_path.join(rel_path_str);

            if full_path.is_file() {
                files.insert(rel_path_str.to_string());
            } else if full_path.is_dir() {
                for entry in WalkDir::new(&full_path).into_iter().filter_map(|e| e.ok()) {
                    if entry.file_type().is_file() {
                        if let Ok(rel) = entry.path().strip_prefix(dcs_path) {
                            // Normalize to forward slashes
                            let rel_str = rel.to_string_lossy().replace('\\', "/");
                            files.insert(rel_str);
                        }
                    }
                }
            }
        }
    }

    files.into_iter().collect()
}

/// Create a backup ZIP archive. Returns the path to the created ZIP.
pub fn create_backup(
    dcs_path: &Path,
    dest_dir: &Path,
    categories: &[BackupCategory],
) -> Result<(String, usize), String> {
    let timestamp = chrono::Local::now().format("%Y-%m-%d_%H%M%S").to_string();
    let zip_name = format!("DCS_Backup_{}.zip", timestamp);
    let zip_path = dest_dir.join(&zip_name);

    let files = collect_files(dcs_path, categories);
    let file_count = files.len();

    // Extract device info if inputs are included
    let devices = if categories.contains(&BackupCategory::Inputs) {
        let input_dir = dcs_path.join("Config").join("Input");
        if input_dir.is_dir() {
            extract_devices_from_input_dir(&input_dir)
        } else {
            vec![]
        }
    } else {
        vec![]
    };

    let dcs_version = get_dcs_version(dcs_path);

    let manifest = BackupManifest {
        app_version: APP_VERSION.to_string(),
        timestamp: chrono::Local::now().to_rfc3339(),
        dcs_version,
        dcs_path: dcs_path.to_string_lossy().to_string(),
        categories: categories.iter().map(|c| serde_json::to_value(c).unwrap().as_str().unwrap().to_string()).collect(),
        files: files.clone(),
        devices,
    };

    let zip_file = File::create(&zip_path).map_err(|e| format!("Failed to create ZIP: {}", e))?;
    let mut zip = ZipWriter::new(zip_file);
    let options = SimpleFileOptions::default().compression_method(zip::CompressionMethod::Deflated);

    for rel_path in &files {
        let full_path = dcs_path.join(rel_path);
        if full_path.is_file() {
            zip.start_file(rel_path, options)
                .map_err(|e| format!("ZIP write error: {}", e))?;
            let mut f = File::open(&full_path)
                .map_err(|e| format!("Failed to read {}: {}", rel_path, e))?;
            let mut buf = Vec::new();
            f.read_to_end(&mut buf)
                .map_err(|e| format!("Read error {}: {}", rel_path, e))?;
            zip.write_all(&buf)
                .map_err(|e| format!("Write error {}: {}", rel_path, e))?;
        }
    }

    // Write manifest
    let manifest_json = serde_json::to_string_pretty(&manifest)
        .map_err(|e| format!("JSON error: {}", e))?;
    zip.start_file("manifest.json", options)
        .map_err(|e| format!("ZIP manifest error: {}", e))?;
    zip.write_all(manifest_json.as_bytes())
        .map_err(|e| format!("Write manifest error: {}", e))?;

    zip.finish().map_err(|e| format!("ZIP finish error: {}", e))?;

    Ok((zip_path.to_string_lossy().to_string(), file_count))
}

/// Read and parse the manifest from a backup ZIP.
pub fn read_manifest_from_zip(zip_path: &Path) -> Result<BackupManifest, String> {
    let file = File::open(zip_path).map_err(|e| format!("Failed to open ZIP: {}", e))?;
    let mut archive = zip::ZipArchive::new(file).map_err(|e| format!("Invalid ZIP: {}", e))?;

    let mut manifest_file = archive
        .by_name("manifest.json")
        .map_err(|_| "No manifest.json found in backup".to_string())?;

    let mut contents = String::new();
    manifest_file
        .read_to_string(&mut contents)
        .map_err(|e| format!("Failed to read manifest: {}", e))?;

    serde_json::from_str(&contents).map_err(|e| format!("Invalid manifest JSON: {}", e))
}
