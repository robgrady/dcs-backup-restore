import { useState, useEffect } from "react";
import { invoke } from "@tauri-apps/api/core";
import BackupTab from "./components/BackupTab";
import RestoreTab from "./components/RestoreTab";
import type { CategoryInfo } from "./types";

type Tab = "backup" | "restore";

function App() {
  const [activeTab, setActiveTab] = useState<Tab>("backup");
  const [dcsPath, setDcsPath] = useState("");
  const [dcsPathValid, setDcsPathValid] = useState(false);
  const [categories, setCategories] = useState<CategoryInfo[]>([]);

  useEffect(() => {
    // Auto-detect DCS path
    invoke<string[]>("cmd_detect_dcs_paths").then((paths) => {
      if (paths.length > 0) {
        setDcsPath(paths[0]);
        setDcsPathValid(true);
      }
    });
    // Load categories
    invoke<CategoryInfo[]>("cmd_get_categories").then(setCategories);
  }, []);

  const onDcsPathChange = async (path: string) => {
    setDcsPath(path);
    if (path) {
      const valid = await invoke<boolean>("cmd_validate_dcs_path", { path });
      setDcsPathValid(valid);
    } else {
      setDcsPathValid(false);
    }
  };

  const browseDcsPath = async () => {
    const { open } = await import("@tauri-apps/plugin-dialog");
    const selected = await open({ directory: true, title: "Select DCS Saved Games Folder" });
    if (selected) {
      onDcsPathChange(selected as string);
    }
  };

  return (
    <div className="min-h-screen flex flex-col p-4">
      {/* DCS Path */}
      <div className="flex items-center gap-2 mb-4">
        <label className="text-sm font-medium whitespace-nowrap">DCS Folder:</label>
        <input
          type="text"
          value={dcsPath}
          onChange={(e) => onDcsPathChange(e.target.value)}
          className={`flex-1 px-3 py-1.5 bg-[#16213e] border rounded text-sm ${
            dcsPath && !dcsPathValid ? "border-red-500" : "border-[#0f3460]"
          }`}
          placeholder="(not found — use Browse)"
        />
        <button
          onClick={browseDcsPath}
          className="px-4 py-1.5 bg-[#0f3460] hover:bg-[#1a4a8a] rounded text-sm transition-colors"
        >
          Browse
        </button>
      </div>

      {/* Tabs */}
      <div className="flex border-b border-[#0f3460] mb-4">
        <button
          onClick={() => setActiveTab("backup")}
          className={`px-6 py-2 text-sm font-medium transition-colors ${
            activeTab === "backup"
              ? "text-blue-400 border-b-2 border-blue-400"
              : "text-gray-400 hover:text-gray-200"
          }`}
        >
          Backup
        </button>
        <button
          onClick={() => setActiveTab("restore")}
          className={`px-6 py-2 text-sm font-medium transition-colors ${
            activeTab === "restore"
              ? "text-blue-400 border-b-2 border-blue-400"
              : "text-gray-400 hover:text-gray-200"
          }`}
        >
          Restore
        </button>
      </div>

      {/* Tab Content */}
      <div className="flex-1 overflow-auto">
        {activeTab === "backup" ? (
          <BackupTab
            dcsPath={dcsPath}
            dcsPathValid={dcsPathValid}
            categories={categories}
          />
        ) : (
          <RestoreTab
            dcsPath={dcsPath}
            dcsPathValid={dcsPathValid}
            categories={categories}
          />
        )}
      </div>
    </div>
  );
}

export default App;
