export interface CategoryInfo {
  id: string;
  label: string;
}

export interface DeviceInfo {
  name: string;
  uuid: string;
}

export interface BackupManifest {
  app_version: string;
  timestamp: string;
  dcs_version: string | null;
  dcs_path: string;
  categories: string[];
  files: string[];
  devices: DeviceInfo[];
}

export interface UUIDMapping {
  device_name: string;
  old_uuid: string;
  new_uuid: string;
}

export interface BackupResult {
  zip_path: string;
  file_count: number;
}

export interface RestoreResult {
  restored_count: number;
  safety_path: string | null;
}
