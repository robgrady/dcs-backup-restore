use std::collections::HashSet;
use std::fs;
use std::io::Read;
use std::path::Path;
use zip::ZipArchive;

use crate::models::{BackupCategory, UUIDMapping};
use crate::uuid_remapper::{remap_file_contents, remap_filename};

/// Determine which BackupCategory a file belongs to.
fn category_for_file(rel_path: &str) -> Option<BackupCategory> {
    let normalized = rel_path.replace('\\', "/");
    for cat in BackupCategory::all() {
        for cat_path in cat.paths() {
            if normalized == cat_path || normalized.starts_with(&format!("{}/", cat_path)) {
                return Some(cat);
            }
        }
    }
    None
}

/// Create a safety backup of current DCS config files before overwriting.
pub fn create_safety_backup(dcs_path: &Path) -> Result<String, String> {
    let timestamp = chrono::Local::now().format("%Y-%m-%d_%H%M%S").to_string();
    let safety_dir = dcs_path.join("_safety_backup").join(&timestamp);

    let config_dir = dcs_path.join("Config");
    if config_dir.is_dir() {
        copy_dir_all(&config_dir, &safety_dir.join("Config"))
            .map_err(|e| format!("Safety backup failed: {}", e))?;
    }

    let kneeboard_dir = dcs_path.join("Kneeboard");
    if kneeboard_dir.is_dir() {
        copy_dir_all(&kneeboard_dir, &safety_dir.join("Kneeboard"))
            .map_err(|e| format!("Safety backup failed: {}", e))?;
    }

    Ok(safety_dir.to_string_lossy().to_string())
}

fn copy_dir_all(src: &Path, dst: &Path) -> std::io::Result<()> {
    fs::create_dir_all(dst)?;
    for entry in fs::read_dir(src)? {
        let entry = entry?;
        let ty = entry.file_type()?;
        let dest = dst.join(entry.file_name());
        if ty.is_dir() {
            copy_dir_all(&entry.path(), &dest)?;
        } else {
            fs::copy(entry.path(), dest)?;
        }
    }
    Ok(())
}

/// Restore files from a backup ZIP into the DCS Saved Games folder.
pub fn restore_backup(
    zip_path: &Path,
    dcs_path: &Path,
    categories: &[BackupCategory],
    uuid_mappings: &[UUIDMapping],
    do_safety_backup: bool,
) -> Result<(usize, Option<String>), String> {
    let selected: HashSet<String> = categories
        .iter()
        .map(|c| serde_json::to_value(c).unwrap().as_str().unwrap().to_string())
        .collect();

    let safety_path = if do_safety_backup {
        Some(create_safety_backup(dcs_path)?)
    } else {
        None
    };

    let file = fs::File::open(zip_path).map_err(|e| format!("Failed to open ZIP: {}", e))?;
    let mut archive = ZipArchive::new(file).map_err(|e| format!("Invalid ZIP: {}", e))?;

    let mut restored_count = 0;

    for i in 0..archive.len() {
        let mut entry = archive.by_index(i).map_err(|e| format!("ZIP entry error: {}", e))?;
        let raw_name = entry.name().to_string();

        if raw_name == "manifest.json" {
            continue;
        }

        let normalized = raw_name.replace('\\', "/");

        // Check if this file belongs to a selected category
        let cat = match category_for_file(&normalized) {
            Some(c) => c,
            None => continue,
        };
        let cat_str = serde_json::to_value(&cat).unwrap().as_str().unwrap().to_string();
        if !selected.contains(&cat_str) {
            continue;
        }

        let mut data = Vec::new();
        entry.read_to_end(&mut data).map_err(|e| format!("Read error: {}", e))?;

        let is_input_file = normalized.starts_with("Config/Input/") && normalized.ends_with(".diff.lua");
        let mut dest_rel = normalized.clone();

        if is_input_file && !uuid_mappings.is_empty() {
            // Remap filename
            if let Some(pos) = dest_rel.rfind('/') {
                let dir_part = &dest_rel[..pos];
                let fname = &dest_rel[pos + 1..];
                let new_fname = remap_filename(fname, uuid_mappings);
                dest_rel = format!("{}/{}", dir_part, new_fname);
            }

            // Remap file contents
            if let Ok(text) = String::from_utf8(data.clone()) {
                let remapped = remap_file_contents(&text, uuid_mappings);
                data = remapped.into_bytes();
            }
        }

        let dest_path = dcs_path.join(&dest_rel);
        if let Some(parent) = dest_path.parent() {
            fs::create_dir_all(parent)
                .map_err(|e| format!("Failed to create dir: {}", e))?;
        }
        fs::write(&dest_path, &data)
            .map_err(|e| format!("Failed to write {}: {}", dest_rel, e))?;

        restored_count += 1;
    }

    Ok((restored_count, safety_path))
}
