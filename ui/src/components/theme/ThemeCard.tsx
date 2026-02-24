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
  return (
    <button
      onClick={() => onSelect(theme)}
      className={cn(
        "group relative w-full rounded-lg border-2 p-3 transition-all hover:scale-[1.02]",
        isSelected
          ? "border-accent-main shadow-lg"
          : "border-border-main hover:border-text-muted"
      )}
    >
      {/* Theme Name */}
      <div className="mb-2 text-left">
        <h3 className="text-xs font-semibold text-text-primary">
          {theme.name}
        </h3>
        <p className="text-[10px] text-text-muted">
          {theme.isDarkMode ? "Dark" : "Light"}
        </p>
      </div>

      {/* Color Swatch Preview */}
      <div className="mb-2 grid grid-cols-2 gap-1 overflow-hidden rounded">
        <div
          className="h-8"
          style={{ backgroundColor: theme.variables["bg-primary"] }}
          title="Background Primary"
        />
        <div
          className="h-8"
          style={{ backgroundColor: theme.variables["bg-secondary"] }}
          title="Background Secondary"
        />
        <div
          className="h-8"
          style={{ backgroundColor: theme.variables["accent-color"] }}
          title="Accent"
        />
        <div
          className="h-8"
          style={{ backgroundColor: theme.variables["success"] }}
          title="Success"
        />
      </div>

      {/* Selected Indicator */}
      {isSelected && (
        <div className="absolute -right-1 -top-1 flex h-6 w-6 items-center justify-center rounded-full bg-accent-main shadow-md">
          <Check size={14} className="text-white" />
        </div>
      )}

      {/* Hover State Indicator */}
      {!isSelected && (
        <div className="absolute inset-0 rounded-lg bg-accent-main/0 transition-colors group-hover:bg-accent-main/5" />
      )}
    </button>
  );
};
