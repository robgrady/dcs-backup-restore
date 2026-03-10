import { useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import type {
  CategoryInfo,
  BackupManifest,
  DeviceInfo,
  UUIDMapping,
  RestoreResult,
} from "../types";

interface Props {
  dcsPath: string;
  dcsPathValid: boolean;
  categories: CategoryInfo[];
}

interface DeviceMappingRow {
  device: DeviceInfo;
  selectedUuid: string; // "" means keep original
}

export default function RestoreTab({ dcsPath, dcsPathValid, categories }: Props) {
  const [zipPath, setZipPath] = useState("");
  const [manifest, setManifest] = useState<BackupManifest | null>(null);
  const [selectedCats, setSelectedCats] = useState<Set<string>>(new Set());
  const [currentDevices, setCurrentDevices] = useState<DeviceInfo[]>([]);
  const [deviceMappings, setDeviceMappings] = useState<DeviceMappingRow[]>([]);
  const [safetyBackup, setSafetyBackup] = useState(true);
  const [running, setRunning] = useState(false);
  const [log, setLog] = useState<string[]>([]);

  const addLog = (msg: string) => setLog((prev) => [...prev, msg]);

  const browseZip = async () => {
    const { open } = await import("@tauri-apps/plugin-dialog");
    const selected = await open({
      title: "Select Backup ZIP",
      filters: [{ name: "ZIP files", extensions: ["zip"] }],
    });
    if (selected) loadManifest(selected as string);
  };

  const loadManifest = async (path: string) => {
    setZipPath(path);
    try {
      const m = await invoke<BackupManifest>("cmd_read_manifest", { zipPath: path });
      setManifest(m);
      setSelectedCats(new Set(m.categories));

      // Detect current devices and auto-match
      if (dcsPathValid && m.devices.length > 0) {
        const current = await invoke<DeviceInfo[]>("cmd_detect_current_devices", { dcsPath });
        setCurrentDevices(current);

        const autoMappings = await invoke<UUIDMapping[]>("cmd_auto_match_devices", {
          backupDevices: m.devices,
          currentDevices: current,
        });
        const autoMap = new Map(autoMappings.map((m) => [m.old_uuid, m.new_uuid]));

        setDeviceMappings(
          m.devices.map((dev) => ({
            device: dev,
            selectedUuid: autoMap.get(dev.uuid) ?? "",
          }))
        );
      }
    } catch (e) {
      addLog(`ERROR: Failed to read backup: ${e}`);
    }
  };

  const toggleCat = (id: string) => {
    setSelectedCats((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const updateDeviceMapping = (index: number, newUuid: string) => {
    setDeviceMappings((prev) =>
      prev.map((row, i) => (i === index ? { ...row, selectedUuid: newUuid } : row))
    );
  };

  const runRestore = async () => {
    if (!dcsPathValid) { addLog("ERROR: Invalid DCS folder."); return; }
    if (!zipPath) { addLog("ERROR: Select a backup ZIP."); return; }
    if (selectedCats.size === 0) { addLog("ERROR: Select at least one category."); return; }

    const uuidMappings: UUIDMapping[] = deviceMappings
      .filter((row) => row.selectedUuid && row.selectedUuid !== row.device.uuid)
      .map((row) => ({
        device_name: row.device.name,
        old_uuid: row.device.uuid,
        new_uuid: row.selectedUuid,
      }));

    setRunning(true);
    setLog([]);
    addLog("Starting restore...");
    if (uuidMappings.length > 0) {
      addLog(`Applying ${uuidMappings.length} UUID remap(s)...`);
    }

    try {
      const result = await invoke<RestoreResult>("cmd_restore_backup", {
        zipPath,
        dcsPath,
        categories: Array.from(selectedCats),
        uuidMappings,
        doSafetyBackup: safetyBackup,
      });
      addLog(`Restored ${result.restored_count} files.`);
      if (result.safety_path) {
        addLog(`Safety backup at: ${result.safety_path}`);
      }
      addLog("Done!");
    } catch (e) {
      addLog(`ERROR: ${e}`);
    } finally {
      setRunning(false);
    }
  };

  const shortUuid = (uuid: string) => uuid.slice(0, 8) + "...";

  return (
    <div className="flex flex-col gap-4">
      {/* ZIP Selection */}
      <div className="flex items-center gap-2">
        <label className="text-sm font-medium whitespace-nowrap">Backup:</label>
        <input
          type="text"
          value={zipPath}
          readOnly
          className="flex-1 px-3 py-1.5 bg-[#16213e] border border-[#0f3460] rounded text-sm"
          placeholder="Select a backup ZIP file..."
        />
        <button
          onClick={browseZip}
          className="px-4 py-1.5 bg-[#0f3460] hover:bg-[#1a4a8a] rounded text-sm transition-colors"
        >
          Browse
        </button>
      </div>

      {/* Manifest Summary */}
      {manifest && (
        <div className="bg-[#16213e] rounded p-3 text-sm">
          <span className="text-gray-400">Backup from </span>
          <span className="text-blue-300">{new Date(manifest.timestamp).toLocaleString()}</span>
          <span className="text-gray-400"> | DCS </span>
          <span className="text-blue-300">{manifest.dcs_version ?? "unknown"}</span>
          <span className="text-gray-400"> | </span>
          <span className="text-blue-300">{manifest.files.length} files</span>
          <span className="text-gray-400"> | App v</span>
          <span className="text-blue-300">{manifest.app_version || "?"}</span>
        </div>
      )}

      {/* Category Selection */}
      {manifest && (
        <div>
          <label className="text-sm font-medium block mb-2">Restore:</label>
          <div className="grid grid-cols-2 gap-1">
            {categories.map((cat) => {
              const inBackup = manifest.categories.includes(cat.id);
              return (
                <label
                  key={cat.id}
                  className={`flex items-center gap-2 text-sm p-1 rounded ${
                    inBackup ? "cursor-pointer hover:bg-[#16213e]" : "opacity-40 cursor-not-allowed"
                  }`}
                >
                  <input
                    type="checkbox"
                    checked={selectedCats.has(cat.id)}
                    onChange={() => toggleCat(cat.id)}
                    disabled={!inBackup}
                    className="accent-blue-500"
                  />
                  {cat.label}
                </label>
              );
            })}
          </div>
        </div>
      )}

      {/* UUID Mapping */}
      {deviceMappings.length > 0 && (
        <div>
          <label className="text-sm font-medium block mb-2">Device UUID Mapping:</label>
          <div className="bg-[#0d1b2a] border border-[#0f3460] rounded overflow-hidden">
            <div className="grid grid-cols-2 gap-2 p-2 bg-[#16213e] text-xs font-bold">
              <div>Backup Device</div>
              <div>Remap To</div>
            </div>
            {deviceMappings.map((row, i) => (
              <div key={i} className="grid grid-cols-2 gap-2 p-2 border-t border-[#0f3460] items-center">
                <div className="text-sm truncate" title={`${row.device.name} [${row.device.uuid}]`}>
                  {row.device.name}{" "}
                  <span className="text-gray-500 text-xs">[{shortUuid(row.device.uuid)}]</span>
                </div>
                <select
                  value={row.selectedUuid}
                  onChange={(e) => updateDeviceMapping(i, e.target.value)}
                  className="bg-[#16213e] border border-[#0f3460] rounded px-2 py-1 text-sm"
                >
                  <option value="">(keep original)</option>
                  {currentDevices.map((dev) => (
                    <option key={dev.uuid} value={dev.uuid}>
                      {dev.name} [{shortUuid(dev.uuid)}]
                    </option>
                  ))}
                </select>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Safety Backup Checkbox */}
      {manifest && (
        <label className="flex items-center gap-2 text-sm cursor-pointer">
          <input
            type="checkbox"
            checked={safetyBackup}
            onChange={(e) => setSafetyBackup(e.target.checked)}
            className="accent-blue-500"
          />
          Create safety backup of current files before restoring
        </label>
      )}

      {/* Restore Button */}
      {manifest && (
        <button
          onClick={runRestore}
          disabled={running}
          className="px-6 py-2.5 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-600 disabled:cursor-not-allowed rounded font-medium transition-colors"
        >
          {running ? "Restoring..." : "Restore"}
        </button>
      )}

      {/* Log */}
      {log.length > 0 && (
        <div className="bg-[#0d1b2a] border border-[#0f3460] rounded p-3 max-h-48 overflow-y-auto">
          {log.map((line, i) => (
            <div key={i} className={`text-xs font-mono ${line.startsWith("ERROR") ? "text-red-400" : line === "Done!" ? "text-green-400" : "text-gray-300"}`}>
              {line}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
