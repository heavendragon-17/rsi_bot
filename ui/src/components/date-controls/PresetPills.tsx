import React, { useEffect } from "react";
import { useBacktestStore } from "../../stores/backtestStore";
import { cn } from "../../lib/utils";

const PRESETS = ["1D", "1W", "1M", "3M", "YTD", "1Y", "All"];

export const PresetPills: React.FC = () => {
  const { datePreset, setDatePreset } = useBacktestStore();

  // Keyboard shortcut 'P' to cycle presets
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key.toLowerCase() === 'p' && !e.ctrlKey && !e.metaKey && !e.altKey && e.target instanceof HTMLElement && e.target.tagName !== 'INPUT') {
        e.preventDefault();
        const currentIndex = datePreset ? PRESETS.indexOf(datePreset) : -1;
        const nextIndex = (currentIndex + 1) % PRESETS.length;
        setDatePreset(PRESETS[nextIndex]);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [datePreset, setDatePreset]);

  return (
    <div className="flex items-center gap-1.5 flex-wrap">
      {PRESETS.map((p) => (
        <button
          key={p}
          onClick={() => setDatePreset(p)}
          className={cn(
            "px-2 py-1 rounded text-[10px] font-medium border transition-all",
            datePreset === p
              ? "bg-accent-main border-accent-main text-white shadow-sm shadow-accent-main/20"
              : "bg-transparent border-border-main text-text-secondary hover:border-text-muted hover:text-text-primary"
          )}
        >
          {p}
        </button>
      ))}
    </div>
  );
};
