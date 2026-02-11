import React from "react";
import { ThemeSelector } from "./ThemeSelector";
import { PerformanceModeToggle } from "./PerformanceModeToggle";
import { RotateCcw } from "lucide-react";
import { useThemeStore } from "../../stores/themeStore";

export const ThemeSettings: React.FC = () => {
  const { themes, setTheme, performanceMode, togglePerformanceMode } =
    useThemeStore();

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
    <div className="space-y-12">
      {/* Appearance Section */}
      <div>
        <ThemeSelector />
      </div>

      {/* Performance Section */}
      <div className="pt-8">
        <PerformanceModeToggle />
      </div>

      {/* Danger Zone */}
      <div className="pt-6">
        <h3 className="mb-3 text-sm font-semibold uppercase tracking-wider text-danger">
          Danger Zone
        </h3>
        <button
          onClick={handleResetSettings}
          className="flex w-full items-center justify-center gap-2 rounded-lg border border-danger/30 bg-danger/5 px-4 py-3 text-sm font-medium text-danger transition-colors hover:bg-danger/10"
        >
          <RotateCcw size={16} />
          Reset All Settings
        </button>
        <p className="mt-2 text-xs text-text-muted">
          This will reset theme and performance settings to defaults
        </p>
      </div>
    </div>
  );
};
