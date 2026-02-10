import React, { useState } from "react";
import { X, ChevronLeft, ChevronRight } from "lucide-react";
import { useThemeStore } from "../../stores/themeStore";
import { ThemeCard } from "./ThemeCard";
import { cn } from "../../lib/utils";

interface AllThemesModalProps {
  isOpen: boolean;
  onClose: () => void;
}

const ITEMS_PER_PAGE = 8;

export const AllThemesModal: React.FC<AllThemesModalProps> = ({
  isOpen,
  onClose,
}) => {
  const { themes, currentTheme, setTheme } = useThemeStore();
  const [currentPage, setCurrentPage] = useState(1);

  const totalPages = Math.ceil(themes.length / ITEMS_PER_PAGE);
  const startIndex = (currentPage - 1) * ITEMS_PER_PAGE;
  const paginatedThemes = themes.slice(startIndex, startIndex + ITEMS_PER_PAGE);

  const handleSelectTheme = (theme: typeof themes[0]) => {
    setTheme(theme);
    onClose();
  };

  const handlePrevPage = () => {
    if (currentPage > 1) setCurrentPage(currentPage - 1);
  };

  const handleNextPage = () => {
    if (currentPage < totalPages) setCurrentPage(currentPage + 1);
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm animate-in fade-in duration-300">
      <div className="relative h-full max-h-[85vh] w-full max-w-4xl overflow-hidden rounded-[2rem] border border-border-main bg-bg-secondary shadow-2xl flex flex-col mx-4 sm:mx-0">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-border-main p-6 sm:p-8 shrink-0">
          <div>
            <h2 className="text-xl font-bold text-text-primary tracking-tight">
              All Themes ({themes.length})
            </h2>
            <p className="text-sm text-text-muted mt-1">
              Browse and select from our high-performance color palettes
            </p>
          </div>
          <button
            onClick={onClose}
            className="rounded-xl p-2 text-text-muted hover:bg-bg-elevated hover:text-text-primary transition-all active:scale-90"
          >
            <X size={24} />
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto custom-scrollbar p-6 sm:p-8">
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
            {paginatedThemes.map((theme) => (
                <ThemeCard
                key={theme.id}
                theme={theme}
                isSelected={currentTheme?.id === theme.id}
                onSelect={handleSelectTheme}
                />
            ))}
            </div>
        </div>

        {/* Footer / Pagination */}
        <div className="border-t border-border-main p-6 sm:p-8 bg-bg-surface/50 flex flex-col sm:flex-row items-center justify-between gap-4 shrink-0">
          <div className="text-sm font-medium text-text-secondary order-2 sm:order-1">
            Displaying <span className="text-text-primary">{startIndex + 1}—{Math.min(startIndex + ITEMS_PER_PAGE, themes.length)}</span> of <span className="text-text-primary">{themes.length}</span> themes
          </div>
          
          <div className="flex items-center gap-2 order-1 sm:order-2">
            <div className="flex items-center gap-1 mr-4">
                <span className="text-sm text-text-muted">Page</span>
                <span className="flex items-center justify-center w-8 h-8 rounded-lg bg-bg-elevated text-sm font-bold text-accent-main border border-accent-main/20">
                    {currentPage}
                </span>
                <span className="text-sm text-text-muted">of {totalPages}</span>
            </div>

            <button
               onClick={handlePrevPage}
               disabled={currentPage === 1}
               className={cn(
                 "p-2 rounded-xl border border-border-main bg-bg-elevated/50 text-text-primary transition-all active:scale-95 disabled:opacity-30 disabled:pointer-events-none hover:bg-bg-elevated hover:border-text-muted",
               )}
            >
               <ChevronLeft size={20} />
            </button>
            <button
               onClick={handleNextPage}
               disabled={currentPage === totalPages}
               className={cn(
                 "p-2 rounded-xl border border-border-main bg-bg-elevated/50 text-text-primary transition-all active:scale-95 disabled:opacity-30 disabled:pointer-events-none hover:bg-bg-elevated hover:border-text-muted",
               )}
            >
               <ChevronRight size={20} />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
