use std::path::{Path, PathBuf};

const DCS_FOLDER_NAMES: &[&str] = &["DCS", "DCS.openbeta"];

pub fn get_saved_games_dir() -> Option<PathBuf> {
    if let Ok(profile) = std::env::var("USERPROFILE") {
        return Some(PathBuf::from(profile).join("Saved Games"));
    }
    dirs::home_dir().map(|h| h.join("Saved Games"))
}

pub fn validate_dcs_path(path: &Path) -> bool {
    path.is_dir() && path.join("Config").is_dir()
}

pub fn detect_dcs_paths() -> Vec<PathBuf> {
    let Some(saved_games) = get_saved_games_dir() else {
        return vec![];
    };
    DCS_FOLDER_NAMES
        .iter()
        .map(|name| saved_games.join(name))
        .filter(|p| validate_dcs_path(p))
        .collect()
}

pub fn get_dcs_version(dcs_path: &Path) -> Option<String> {
    let autoupdate = dcs_path.join("autoupdate.cfg");
    let text = std::fs::read_to_string(autoupdate).ok()?;
    for line in text.lines() {
        if line.contains("\"version\"") || line.contains("'version'") {
            let parts: Vec<&str> = line.split('"').collect();
            if parts.len() >= 4 {
                return Some(parts[3].to_string());
            }
        }
    }
    None
}
