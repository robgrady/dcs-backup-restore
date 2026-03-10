use serde::{Deserialize, Serialize};

pub const APP_VERSION: &str = "1.0.0";

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq, Hash)]
pub enum BackupCategory {
    #[serde(rename = "settings")]
    Settings,
    #[serde(rename = "overrides")]
    Overrides,
    #[serde(rename = "inputs")]
    Inputs,
    #[serde(rename = "monitors")]
    Monitors,
    #[serde(rename = "server")]
    Server,
    #[serde(rename = "kneeboards")]
    Kneeboards,
    #[serde(rename = "snapviews")]
    Snapviews,
    #[serde(rename = "missioneditor")]
    MissionEditor,
}

impl BackupCategory {
    pub fn label(&self) -> &'static str {
        match self {
            Self::Settings => "Graphics / Audio / Gameplay Settings",
            Self::Overrides => "Autoexec Overrides",
            Self::Inputs => "Input Bindings (Peripherals)",
            Self::Monitors => "Monitor Setup",
            Self::Server => "Server Settings",
            Self::Kneeboards => "Custom Kneeboards",
            Self::Snapviews => "Snap Views",
            Self::MissionEditor => "Mission Editor Preferences",
        }
    }

    pub fn paths(&self) -> Vec<&'static str> {
        match self {
            Self::Settings => vec!["Config/options.lua"],
            Self::Overrides => vec!["Config/autoexec.cfg"],
            Self::Inputs => vec!["Config/Input"],
            Self::Monitors => vec!["Config/MonitorSetup"],
            Self::Server => vec!["Config/serverSettings.lua"],
            Self::Kneeboards => vec!["Kneeboard"],
            Self::Snapviews => vec!["Config/View"],
            Self::MissionEditor => vec!["Config/missionEditor.lua"],
        }
    }

    pub fn all() -> Vec<BackupCategory> {
        vec![
            Self::Settings,
            Self::Overrides,
            Self::Inputs,
            Self::Monitors,
            Self::Server,
            Self::Kneeboards,
            Self::Snapviews,
            Self::MissionEditor,
        ]
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq, Hash)]
pub struct DeviceInfo {
    pub name: String,
    pub uuid: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BackupManifest {
    pub app_version: String,
    pub timestamp: String,
    pub dcs_version: Option<String>,
    pub dcs_path: String,
    pub categories: Vec<String>,
    pub files: Vec<String>,
    pub devices: Vec<DeviceInfo>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct UUIDMapping {
    pub device_name: String,
    pub old_uuid: String,
    pub new_uuid: String,
}

/// Info sent to the frontend about available categories
#[derive(Debug, Serialize)]
pub struct CategoryInfo {
    pub id: String,
    pub label: String,
}
