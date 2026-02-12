import React, { useEffect } from "react";
import { useBacktestStore } from "../../stores/backtestStore";
import { cn } from "../../lib/utils";

import { motion } from "motion/react";

const PRESETS = ["1D", "1W", "1M", "3M", "YTD", "1Y", "All"];

export const PresetPills: React.FC = () => {
  const { datePreset, setDatePreset } = useBacktestStore();

  // Keyboard shortcut 'P' to cycle presets
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (
        e.key.toLowerCase() === "p" &&
        !e.ctrlKey &&
        !e.metaKey &&
        !e.altKey &&
        e.target instanceof HTMLElement &&
        e.target.tagName !== "INPUT"
      ) {
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
        <motion.button
          key={p}
          whileHover={{ scale: 1.05 }}
          whileTap={{ scale: 0.95 }}
          onClick={() => setDatePreset(p)}
          className={cn(
            "px-2.5 py-1 rounded-md text-[10px] font-bold border transition-all duration-300",
            datePreset === p
              ? "bg-accent-main/20 border-accent-main text-accent-main shadow-[0_0_15px_rgba(var(--color-accent-main-rgb),0.1)]"
              : "bg-white/5 backdrop-blur-md border-white/10 text-text-secondary hover:border-white/30 hover:text-text-primary hover:bg-white/10"
          )}
        >
          {p}
        </motion.button>
      ))}
    </div>
  );
};
