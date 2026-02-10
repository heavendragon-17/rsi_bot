import React from "react";
import { useThemeStore } from "../../stores/themeStore";
import { ThemeCard } from "./ThemeCard";
import { AllThemesModal } from "./AllThemesModal";

export const ThemeSelector: React.FC = () => {
  const { themes, currentTheme, setTheme } = useThemeStore();
  const [showAll, setShowAll] = React.useState(false);
  
  // Display only first 6 themes (fills horizontal space better)
  const displayedThemes = themes.slice(0, 6);

  return (
    <div className="space-y-6">
      <label className="block text-sm font-medium text-text-secondary">
        Select Theme
      </label>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
        {displayedThemes.map((theme) => (
            <ThemeCard
            key={theme.id}
            theme={theme}
            isSelected={currentTheme?.id === theme.id}
            onSelect={setTheme}
            />
        ))}
      </div>

      {themes.length > 4 && (
        <button 
            onClick={() => setShowAll(true)}
            className="flex w-full items-center justify-center gap-2 rounded-lg border border-border-main bg-bg-elevated/50 px-4 py-3 text-sm font-medium text-text-primary transition-colors hover:bg-bg-elevated hover:text-accent-main"
        >
            View all {themes.length} themes
        </button>
      )}

       {/* All Themes Modal */}
       {showAll && (
        <AllThemesModal
          isOpen={showAll}
          onClose={() => setShowAll(false)}
        />
      )}
    </div>
  );
};
