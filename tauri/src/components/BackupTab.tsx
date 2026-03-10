import { useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import type { CategoryInfo, BackupResult } from "../types";

interface Props {
  dcsPath: string;
  dcsPathValid: boolean;
  categories: CategoryInfo[];
}

export default function BackupTab({ dcsPath, dcsPathValid, categories }: Props) {
  const [destDir, setDestDir] = useState("");
  const [selectedCats, setSelectedCats] = useState<Set<string>>(
    new Set(["settings", "overrides", "inputs", "monitors", "server", "kneeboards", "snapviews", "missioneditor"])
  );
  const [running, setRunning] = useState(false);
  const [log, setLog] = useState<string[]>([]);

  const toggleCat = (id: string) => {
    setSelectedCats((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const browseDest = async () => {
    const { open } = await import("@tauri-apps/plugin-dialog");
    const selected = await open({ directory: true, title: "Select Backup Destination" });
    if (selected) setDestDir(selected as string);
  };

  const addLog = (msg: string) => setLog((prev) => [...prev, msg]);

  const runBackup = async () => {
    if (!dcsPathValid) { addLog("ERROR: Invalid DCS folder."); return; }
    if (!destDir) { addLog("ERROR: Select a backup destination."); return; }
    if (selectedCats.size === 0) { addLog("ERROR: Select at least one category."); return; }

    setRunning(true);
    setLog([]);
    addLog("Starting backup...");

    try {
      const result = await invoke<BackupResult>("cmd_create_backup", {
        dcsPath,
        destDir,
        categories: Array.from(selectedCats),
      });
      addLog(`Backed up ${result.file_count} files.`);
      addLog(`Saved to: ${result.zip_path}`);
      addLog("Done!");
    } catch (e) {
      addLog(`ERROR: ${e}`);
    } finally {
      setRunning(false);
    }
  };

  return (
    <div className="flex flex-col gap-4">
      {/* Destination */}
      <div className="flex items-center gap-2">
        <label className="text-sm font-medium whitespace-nowrap">Save to:</label>
        <input
          type="text"
          value={destDir}
          onChange={(e) => setDestDir(e.target.value)}
          className="flex-1 px-3 py-1.5 bg-[#16213e] border border-[#0f3460] rounded text-sm"
          placeholder="Select backup destination folder..."
        />
        <button
          onClick={browseDest}
          className="px-4 py-1.5 bg-[#0f3460] hover:bg-[#1a4a8a] rounded text-sm transition-colors"
        >
          Browse
        </button>
      </div>

      {/* Categories */}
      <div>
        <label className="text-sm font-medium block mb-2">Include:</label>
        <div className="grid grid-cols-2 gap-1">
          {categories.map((cat) => (
            <label key={cat.id} className="flex items-center gap-2 text-sm cursor-pointer hover:bg-[#16213e] p-1 rounded">
              <input
                type="checkbox"
                checked={selectedCats.has(cat.id)}
                onChange={() => toggleCat(cat.id)}
                className="accent-blue-500"
              />
              {cat.label}
            </label>
          ))}
        </div>
      </div>

      {/* Backup Button */}
      <button
        onClick={runBackup}
        disabled={running}
        className="px-6 py-2.5 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-600 disabled:cursor-not-allowed rounded font-medium transition-colors"
      >
        {running ? "Backing up..." : "Create Backup"}
      </button>

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
