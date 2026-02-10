import React from "react";
import { X } from "lucide-react";
import { useThemeStore } from "../../stores/themeStore";
import { ThemeCard } from "./ThemeCard";

interface AllThemesModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export const AllThemesModal: React.FC<AllThemesModalProps> = ({
  isOpen,
  onClose,
}) => {
  const { themes, currentTheme, setTheme } = useThemeStore();

  const darkThemes = themes.filter((t) => t.isDarkMode);
  const lightThemes = themes.filter((t) => !t.isDarkMode);

  const handleSelectTheme = (theme: typeof themes[0]) => {
    setTheme(theme);
    onClose();
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="relative max-h-[80vh] w-full max-w-3xl overflow-hidden rounded-xl border border-border-main bg-bg-secondary shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-border-main p-4">
          <div>
            <h2 className="text-sm font-semibold text-text-primary">
              All Themes ({themes.length})
            </h2>
            <p className="text-xs text-text-muted">
              Select a theme to apply instantly
            </p>
          </div>
          <button
            onClick={onClose}
            className="rounded-md p-1.5 text-text-muted hover:bg-bg-elevated hover:text-text-primary transition-colors"
          >
            <X size={18} />
          </button>
        </div>

        {/* Content */}
        <div className="max-h-[calc(80vh-5rem)] overflow-y-auto custom-scrollbar p-4">
          {/* Dark Themes */}
          {darkThemes.length > 0 && (
            <div className="mb-6">
              <h3 className="mb-3 text-xs font-semibold uppercase tracking-wider text-text-muted">
                Dark Themes
              </h3>
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4">
                {darkThemes.map((theme) => (
                  <ThemeCard
                    key={theme.id}
                    theme={theme}
                    isSelected={currentTheme?.id === theme.id}
                    onSelect={handleSelectTheme}
                  />
                ))}
              </div>
            </div>
          )}

          {/* Light Themes */}
          {lightThemes.length > 0 && (
            <div>
              <h3 className="mb-3 text-xs font-semibold uppercase tracking-wider text-text-muted">
                Light Themes
              </h3>
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4">
                {lightThemes.map((theme) => (
                  <ThemeCard
                    key={theme.id}
                    theme={theme}
                    isSelected={currentTheme?.id === theme.id}
                    onSelect={handleSelectTheme}
                  />
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
