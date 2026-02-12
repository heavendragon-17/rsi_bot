import React, { useState } from "react";
import {
  Zap,
  Moon,
  Sun,
  Settings,
  History,
  GitCompare,
  Palette,
  Flame,
  TrendingUp,
  Wind,
} from "lucide-react";
import { cn } from "../../lib/utils";
import { useThemeStore } from "../../stores/themeStore";
import { useBacktestStore } from "../../stores/backtestStore";

import { DevTools } from "../dev/DevTools";

export const Navbar: React.FC = () => {
  const {
    currentTheme,
    themes,
    setTheme,
    performanceMode,
    togglePerformanceMode,
  } = useThemeStore();
  const { mode, setMode } = useBacktestStore();
  const [showThemeMenu, setShowThemeMenu] = useState(false);

  // Cycle through themes (light/dark toggle behavior)
  const cycleTheme = () => {
    if (!currentTheme || themes.length === 0) return;

    const currentIndex = themes.findIndex((t) => t.id === currentTheme.id);
    const nextIndex = (currentIndex + 1) % themes.length;
    setTheme(themes[nextIndex]);
  };

  return (
    <nav className="fixed top-2 sm:top-4 left-2 sm:left-4 right-2 sm:right-4 h-14 z-50 rounded-xl bg-bg-surface/80 backdrop-blur-md border border-bg-elevated/50 shadow-sm flex items-center justify-between px-3 sm:px-4 transition-all duration-300">
      <div className="flex items-center gap-2 sm:gap-4">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-lg bg-accent-main flex items-center justify-center text-white font-bold text-sm">
            SC
          </div>
          <span className="font-semibold text-text-primary hidden sm:block text-sm">
            Strategy Command
          </span>
        </div>

        <div className="h-6 w-px bg-border-main mx-1 sm:mx-2 hidden md:block" />

        <div className="hidden md:flex items-center gap-1">
          <button
            onClick={() => setMode("grid-search")}
            className={cn(
              "p-2 rounded-md transition-colors",
              mode === "grid-search"
                ? "text-accent-main bg-accent-main/10"
                : "text-text-secondary hover:text-text-primary hover:bg-bg-elevated"
            )}
            title="Grid Search"
          >
            <Flame size={18} />
          </button>
          <button
            onClick={() => setMode("walk-forward")}
            className={cn(
              "p-2 rounded-md transition-colors",
              mode === "walk-forward"
                ? "text-accent-main bg-accent-main/10"
                : "text-text-secondary hover:text-text-primary hover:bg-bg-elevated"
            )}
            title="Walk-Forward Optimization"
          >
            <TrendingUp size={18} />
          </button>
          <button
            onClick={() => setMode("sensitivity")}
            className={cn(
              "p-2 rounded-md transition-colors",
              mode === "sensitivity"
                ? "text-accent-main bg-accent-main/10"
                : "text-text-secondary hover:text-text-primary hover:bg-bg-elevated"
            )}
            title="Sensitivity Analysis"
          >
            <Wind size={18} />
          </button>
          <button
            onClick={() => setMode("history")}
            className={cn(
              "p-2 rounded-md transition-colors",
              mode === "history"
                ? "text-accent-main bg-accent-main/10"
                : "text-text-secondary hover:text-text-primary hover:bg-bg-elevated"
            )}
            title="View Run History"
          >
            <History size={18} />
          </button>
          <button className="p-2 rounded-md text-text-secondary hover:text-text-primary hover:bg-bg-elevated transition-colors">
            <GitCompare size={18} />
          </button>
        </div>
      </div>

      <div className="flex items-center gap-1 sm:gap-2">
        {/* Current Theme Badge */}
        {currentTheme && (
          <div className="hidden lg:flex items-center gap-2 px-2 sm:px-3 py-1.5 rounded-md bg-bg-elevated text-xs text-text-secondary">
            <div
              className="w-3 h-3 rounded-full border border-border-main"
              style={{
                backgroundColor: currentTheme.variables["accent-color"],
              }}
            />
            <span className="font-medium">{currentTheme.name}</span>
          </div>
        )}

        {/* Performance Mode Toggle */}
        <button
          onClick={togglePerformanceMode}
          className={cn(
            "flex items-center gap-1 sm:gap-2 px-2 sm:px-3 py-1.5 rounded-md text-xs font-medium transition-all min-h-[44px] sm:min-h-0",
            performanceMode
              ? "bg-warning/20 text-warning border border-warning/30"
              : "bg-bg-elevated text-text-secondary hover:text-text-primary"
          )}
          title="Toggle Performance Mode (Disables Animations)"
        >
          <Zap size={14} className={cn(performanceMode && "fill-current")} />
          <span className="hidden sm:inline">Perf</span>
        </button>

        {/* Theme Toggle */}
        <button
          onClick={cycleTheme}
          className="p-2 rounded-md text-text-secondary hover:text-text-primary hover:bg-bg-elevated transition-colors min-h-[44px] min-w-[44px] flex items-center justify-center"
          title={`Current: ${currentTheme?.name || "Default"} - Click to cycle`}
        >
          {currentTheme?.isDarkMode ? <Moon size={18} /> : <Sun size={18} />}
        </button>

        <button
          onClick={() => setMode("settings")}
          className={cn(
            "hidden sm:flex p-2 rounded-md transition-colors items-center justify-center",
            mode === "settings"
              ? "text-accent-main bg-accent-main/10"
              : "text-text-secondary hover:text-text-primary hover:bg-bg-elevated"
          )}
          title="Settings"
        >
          <Settings size={18} />
        </button>

        <div className="w-px h-6 bg-border-main mx-1" />
        <DevTools />
      </div>
    </nav>
  );
};
