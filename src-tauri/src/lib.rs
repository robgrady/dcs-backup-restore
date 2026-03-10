mod backup;
mod commands;
mod dcs_paths;
mod models;
mod restore;
mod uuid_remapper;

use commands::*;

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .setup(|app| {
            if cfg!(debug_assertions) {
                app.handle().plugin(
                    tauri_plugin_log::Builder::default()
                        .level(log::LevelFilter::Info)
                        .build(),
                )?;
            }
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            cmd_detect_dcs_paths,
            cmd_validate_dcs_path,
            cmd_get_categories,
            cmd_create_backup,
            cmd_read_manifest,
            cmd_detect_current_devices,
            cmd_auto_match_devices,
            cmd_restore_backup,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
