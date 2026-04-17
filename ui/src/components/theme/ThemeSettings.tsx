import React, { useState, useEffect } from "react";
import { ThemeSelector } from "./ThemeSelector";
import { PerformanceModeToggle } from "./PerformanceModeToggle";
import { RotateCcw, Loader2 } from "lucide-react";
import { useThemeStore } from "../../stores/themeStore";
import { apiFetch, ApiError } from "../../api/client";
import { toast } from "sonner";

export const ThemeSettings: React.FC = () => {
  const { themes, setTheme, performanceMode, togglePerformanceMode } = useThemeStore();

  // Concurrency settings
  const [maxWorkers, setMaxWorkers] = useState(2);
  const [isSavingWorkers, setIsSavingWorkers] = useState(false);

  useEffect(() => {
    apiFetch<{ max_workers: number }>("/api/settings/concurrency")
      .then((r) => setMaxWorkers(r.max_workers))
      .catch(() => {});
  }, []);

  const handleSaveConcurrency = async () => {
    setIsSavingWorkers(true);
    try {
      const res = await apiFetch<{ max_workers: number }>(
        "/api/settings/concurrency",
        {
          method: "PUT",
          body: JSON.stringify({ max_workers: maxWorkers }),
        },
      );
      setMaxWorkers(res.max_workers);
      toast.success("Concurrency updated");
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        toast.error("Cannot change while backtests are running");
      } else {
        toast.error("Failed to update concurrency");
      }
    } finally {
      setIsSavingWorkers(false);
    }
  };

  const handleResetSettings = () => {
    // Reset to default theme (Cyberpunk Neon)
    const defaultTheme = themes.find((t) => t.id === "cyberpunk-neon");
    if (defaultTheme) {
      setTheme(defaultTheme);
    }

    // Reset performance mode to off if it's on
    if (performanceMode) {
      togglePerformanceMode();
    }
  };

  return (
    <div className="space-y-6">
      {/* Appearance Section */}
      <div>
        <h3 className="mb-3 text-xs font-semibold uppercase tracking-wider text-text-muted">
          Appearance
        </h3>
        <ThemeSelector />
      </div>

      {/* Performance Section */}
      <div>
        <PerformanceModeToggle />
      </div>

      {/* Concurrency Section */}
      <div className="border-t border-border-main pt-6">
        <h3 className="mb-3 text-xs font-semibold uppercase tracking-wider text-text-muted">
          Performance
        </h3>
        <div className="flex items-center gap-3">
          <label className="text-xs text-text-secondary whitespace-nowrap">
            Max Workers
          </label>
          <input
            type="number"
            min={1}
            max={8}
            value={maxWorkers}
            onChange={(e) => setMaxWorkers(parseInt(e.target.value) || 1)}
            className="w-16 rounded-md border border-border-main bg-bg-elevated px-2 py-1.5 text-xs text-text-primary text-center"
          />
          <button
            onClick={handleSaveConcurrency}
            disabled={isSavingWorkers}
            className="rounded-md bg-accent-main/20 px-3 py-1.5 text-xs font-medium text-accent-main transition-colors hover:bg-accent-main/30 disabled:opacity-50"
          >
            {isSavingWorkers ? (
              <Loader2 size={12} className="animate-spin" />
            ) : (
              "Save"
            )}
          </button>
        </div>
        <p className="mt-2 text-[10px] text-text-muted">
          Max concurrent backtest jobs (1–8). Cannot change while jobs are running.
        </p>
      </div>

      {/* Danger Zone */}
      <div className="border-t border-border-main pt-6">
        <h3 className="mb-3 text-xs font-semibold uppercase tracking-wider text-danger">
          Danger Zone
        </h3>
        <button
          onClick={handleResetSettings}
          className="flex w-full items-center justify-center gap-2 rounded-lg border border-danger/30 bg-danger/5 px-4 py-2.5 text-xs font-medium text-danger transition-colors hover:bg-danger/10"
        >
          <RotateCcw size={14} />
          Reset All Settings
        </button>
        <p className="mt-2 text-[10px] text-text-muted">
          This will reset theme and performance settings to defaults
        </p>
      </div>
    </div>
  );
};
