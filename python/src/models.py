"""Data models for DCS Backup & Restore."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import json

from .version import __version__


class BackupCategory(Enum):
    """Categories of files that can be backed up."""
    SETTINGS = "settings"          # Config/options.lua
    OVERRIDES = "overrides"        # Config/autoexec.cfg
    INPUTS = "inputs"              # Config/Input/**/*.diff.lua
    MONITORS = "monitors"          # Config/MonitorSetup/
    SERVER = "server"              # Config/serverSettings.lua
    KNEEBOARDS = "kneeboards"      # Kneeboard/
    SNAPVIEWS = "snapviews"        # Config/View/
    MISSION_EDITOR = "missioneditor"  # Config/missionEditor.lua


# Human-readable labels for each category
CATEGORY_LABELS = {
    BackupCategory.SETTINGS: "Graphics / Audio / Gameplay Settings",
    BackupCategory.OVERRIDES: "Autoexec Overrides",
    BackupCategory.INPUTS: "Input Bindings (Peripherals)",
    BackupCategory.MONITORS: "Monitor Setup",
    BackupCategory.SERVER: "Server Settings",
    BackupCategory.KNEEBOARDS: "Custom Kneeboards",
    BackupCategory.SNAPVIEWS: "Snap Views",
    BackupCategory.MISSION_EDITOR: "Mission Editor Preferences",
}

# Map categories to their relative paths within the DCS Saved Games folder
CATEGORY_PATHS: dict[BackupCategory, list[str]] = {
    BackupCategory.SETTINGS: ["Config/options.lua"],
    BackupCategory.OVERRIDES: ["Config/autoexec.cfg"],
    BackupCategory.INPUTS: ["Config/Input"],
    BackupCategory.MONITORS: ["Config/MonitorSetup"],
    BackupCategory.SERVER: ["Config/serverSettings.lua"],
    BackupCategory.KNEEBOARDS: ["Kneeboard"],
    BackupCategory.SNAPVIEWS: ["Config/View"],
    BackupCategory.MISSION_EDITOR: ["Config/missionEditor.lua"],
}


@dataclass
class DeviceInfo:
    """Represents a detected input device with its name and UUID."""
    name: str
    uuid: str

    def to_dict(self) -> dict:
        return {"name": self.name, "uuid": self.uuid}

    @classmethod
    def from_dict(cls, data: dict) -> "DeviceInfo":
        return cls(name=data["name"], uuid=data["uuid"])


@dataclass
class BackupManifest:
    """Metadata stored inside each backup ZIP."""
    timestamp: str
    dcs_version: str | None
    dcs_path: str
    categories: list[str]
    files: list[str]
    devices: list[DeviceInfo] = field(default_factory=list)
    app_version: str = ""

    def to_json(self) -> str:
        return json.dumps({
            "app_version": self.app_version,
            "timestamp": self.timestamp,
            "dcs_version": self.dcs_version,
            "dcs_path": self.dcs_path,
            "categories": self.categories,
            "files": self.files,
            "devices": [d.to_dict() for d in self.devices],
        }, indent=2)

    @classmethod
    def from_json(cls, text: str) -> "BackupManifest":
        data = json.loads(text)
        return cls(
            timestamp=data["timestamp"],
            dcs_version=data.get("dcs_version"),
            dcs_path=data["dcs_path"],
            categories=data["categories"],
            files=data["files"],
            devices=[DeviceInfo.from_dict(d) for d in data.get("devices", [])],
            app_version=data.get("app_version", ""),
        )

    @classmethod
    def create(
        cls,
        dcs_path: str,
        dcs_version: str | None,
        categories: list[BackupCategory],
        files: list[str],
        devices: list[DeviceInfo],
    ) -> "BackupManifest":
        return cls(
            timestamp=datetime.now().isoformat(),
            dcs_version=dcs_version,
            dcs_path=dcs_path,
            categories=[c.value for c in categories],
            files=files,
            devices=devices,
            app_version=__version__,
        )


@dataclass
class UUIDMapping:
    """Maps an old device UUID to a new one for restore."""
    device_name: str
    old_uuid: str
    new_uuid: str
