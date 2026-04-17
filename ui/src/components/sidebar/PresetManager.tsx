import React, { useEffect, useState } from "react";
import { Save, Trash2, Upload } from "lucide-react";
import { usePresetStore } from "../../stores/presetStore";
import { useBacktestStore } from "../../stores/backtestStore";
import { CollapsibleSection } from "../ui/CollapsibleSection";
import { cn } from "../../lib/utils";

export const PresetManager: React.FC = () => {
  const { presets, isLoading, fetchPresets, savePreset, loadPreset, deletePreset } =
    usePresetStore();
  const strategy = useBacktestStore((s) => s.strategy);
  const [newName, setNewName] = useState("");
  const [isSaving, setIsSaving] = useState(false);

  useEffect(() => {
    fetchPresets(strategy);
  }, [strategy, fetchPresets]);

  const handleSave = async () => {
    const name = newName.trim();
    if (!name) return;
    setIsSaving(true);
    try {
      await savePreset(name);
      setNewName("");
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <CollapsibleSection title="Presets" defaultOpen={false}>
      <div className="space-y-2">
        {/* Save Current */}
        <div className="flex gap-2">
          <input
            type="text"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleSave()}
            placeholder="Preset name..."
            className="flex-1 bg-input/50 border border-border-main rounded-md px-2 py-1.5 text-xs text-text-primary placeholder:text-text-muted focus:outline-none focus:ring-1 focus:ring-accent-main/50"
          />
          <button
            onClick={handleSave}
            disabled={!newName.trim() || isSaving}
            className={cn(
              "px-2 py-1.5 rounded-md text-xs font-medium transition-colors flex items-center gap-1",
              newName.trim()
                ? "bg-accent-main/10 text-accent-main hover:bg-accent-main/20"
                : "bg-bg-elevated text-text-muted cursor-not-allowed"
            )}
          >
            <Save size={12} />
            Save
          </button>
        </div>

        {/* Preset List */}
        {isLoading ? (
          <div className="text-xs text-text-muted py-2 text-center">Loading...</div>
        ) : presets.length === 0 ? (
          <div className="text-xs text-text-muted py-2 text-center">
            No presets saved for this strategy
          </div>
        ) : (
          <div className="space-y-1 max-h-40 overflow-y-auto custom-scrollbar">
            {presets.map((preset) => (
              <div
                key={preset.id}
                className="flex items-center justify-between py-1.5 px-2 rounded-md bg-bg-elevated/50 hover:bg-bg-elevated transition-colors group"
              >
                <button
                  onClick={() => loadPreset(preset)}
                  className="flex items-center gap-1.5 text-xs text-text-secondary hover:text-text-primary transition-colors flex-1 text-left"
                >
                  <Upload size={11} className="shrink-0" />
                  <span className="truncate">{preset.name}</span>
                </button>
                <button
                  onClick={() => deletePreset(preset.id)}
                  className="opacity-0 group-hover:opacity-100 p-1 rounded hover:bg-red-500/10 text-text-muted hover:text-red-400 transition-all"
                >
                  <Trash2 size={11} />
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </CollapsibleSection>
  );
};
