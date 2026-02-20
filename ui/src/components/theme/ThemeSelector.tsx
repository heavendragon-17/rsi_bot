import React, { useState } from "react";
import { ArrowRight } from "lucide-react";
import { useThemeStore } from "../../stores/themeStore";
import { ThemeCard } from "./ThemeCard";
import { AllThemesModal } from "./AllThemesModal";

export const ThemeSelector: React.FC = () => {
  const { themes, currentTheme, setTheme } = useThemeStore();
  const [showAllModal, setShowAllModal] = useState(false);

  // Show first 4 themes in the main view
  const displayedThemes = themes.slice(0, 4);
  const hasMoreThemes = themes.length > 4;

  return (
    <div className="space-y-3">
      <div>
        <label className="mb-2 block text-xs font-medium text-text-secondary">
          Theme
        </label>
        <div className="grid grid-cols-2 gap-2 p-1 -m-1">
          {displayedThemes.map((theme) => (
            <ThemeCard
              key={theme.id}
              theme={theme}
              isSelected={currentTheme?.id === theme.id}
              onSelect={setTheme}
            />
          ))}
        </div>
      </div>

      {/* View All Button */}
      {hasMoreThemes && (
        <button
          onClick={() => setShowAllModal(true)}
          className="flex w-full items-center justify-end gap-1 text-xs text-accent-main hover:text-accent-hover transition-colors"
        >
          <span>
            Showing {displayedThemes.length} of {themes.length} themes
          </span>
          <ArrowRight size={12} />
        </button>
      )}

      {/* All Themes Modal */}
      {showAllModal && (
        <AllThemesModal
          isOpen={showAllModal}
          onClose={() => setShowAllModal(false)}
        />
      )}
    </div>
  );
};
