import React from "react";
import { Check } from "lucide-react";
import { Theme } from "../../stores/themeStore";
import { cn } from "../../lib/utils";

interface ThemeCardProps {
  theme: Theme;
  isSelected: boolean;
  onSelect: (theme: Theme) => void;
}

export const ThemeCard: React.FC<ThemeCardProps> = ({
  theme,
  isSelected,
  onSelect,
}) => {
  const vars = theme.variables;

  return (
    <button
      onClick={() => onSelect(theme)}
      className={cn(
        "group relative w-full overflow-hidden rounded-2xl border transition-all text-left bg-bg-surface p-4 flex flex-col gap-4",
        isSelected
          ? "border-accent-main ring-1 ring-accent-main/50 scale-[1.02] z-10 shadow-[0_0_20px_rgba(var(--accent-rgb),0.3)] bg-bg-elevated/40"
          : "border-border-main hover:border-text-muted hover:bg-bg-elevated/50"
      )}
      style={{
        boxShadow: isSelected ? `0 0 20px -5px ${vars["accent-color"]}40, 0 8px 20px -10px rgba(0,0,0,0.5)` : undefined
      }}
    >
      {/* Theme Header Info */}
      <div className="flex flex-col">
        <span className="text-base font-bold text-text-primary">
          {theme.name}
        </span>
        <span className="text-sm text-text-muted">
          {theme.isDarkMode ? "Dark" : "Light"}
        </span>
      </div>

      {/* 4-Color Grid - Matches reference image */}
      <div className="grid grid-cols-2 gap-2 w-full h-24">
        <div 
          className="h-full w-full rounded-lg ring-1 ring-black/5 dark:ring-white/5" 
          style={{ backgroundColor: vars["bg-primary"] }} 
        />
        <div 
          className="h-full w-full rounded-lg ring-1 ring-black/5 dark:ring-white/5" 
          style={{ backgroundColor: vars["bg-secondary"] }} 
        />
        <div 
          className="h-full w-full rounded-lg ring-1 ring-black/5 dark:ring-white/5" 
          style={{ backgroundColor: vars["accent-color"] }} 
        />
        <div 
          className="h-full w-full rounded-lg ring-1 ring-black/5 dark:ring-white/5" 
          style={{ backgroundColor: vars["bg-elevated"] }} 
        />
      </div>
    </button>
  );
};
