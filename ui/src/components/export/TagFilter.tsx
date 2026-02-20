import React from "react";
import { Star, AlertTriangle, BookOpen, Lightbulb, Clover, Skull, StickyNote } from "lucide-react";
import { useExportStore, TradeTag } from "../../stores/exportStore";
import { cn } from "../../lib/utils";

interface TagFilterProps {
  filteredCount: number;
  totalCount: number;
}

export const TagFilter: React.FC<TagFilterProps> = ({ filteredCount, totalCount }) => {
  const { tagFilters, toggleTagFilter, clearTagFilters, showOnlyWithNotes, setShowOnlyWithNotes } = useExportStore();

  const tagOptions: { tag: TradeTag; icon: any; label: string; color: string }[] = [
    { tag: "star", icon: Star, label: "Starred", color: "text-yellow-400 border-yellow-400/30" },
    { tag: "review", icon: AlertTriangle, label: "Review", color: "text-orange-400 border-orange-400/30" },
    { tag: "learning", icon: BookOpen, label: "Learning", color: "text-blue-400 border-blue-400/30" },
    { tag: "idea", icon: Lightbulb, label: "Ideas", color: "text-purple-400 border-purple-400/30" },
    { tag: "lucky", icon: Clover, label: "Lucky", color: "text-green-400 border-green-400/30" },
    { tag: "unlucky", icon: Skull, label: "Unlucky", color: "text-red-400 border-red-400/30" },
  ];

  const hasActiveFilters = tagFilters.length > 0 || showOnlyWithNotes;

  return (
    <div className="p-4 bg-bg-elevated border-b border-border-main space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-xs font-semibold text-text-secondary uppercase tracking-wider">
          Filters: Tags
        </h3>
        {hasActiveFilters && (
          <button
            onClick={() => {
              clearTagFilters();
            }}
            className="text-xs text-accent-main hover:text-accent-main/80 font-medium"
          >
            Clear All
          </button>
        )}
      </div>

      <div className="flex flex-wrap gap-2">
        {/* All */}
        <button
          onClick={() => clearTagFilters()}
          className={cn(
            "px-3 py-1.5 rounded-lg border text-xs font-medium transition-all",
            !hasActiveFilters
              ? "bg-accent-main/20 border-accent-main text-accent-main"
              : "bg-bg-surface border-border-main text-text-muted hover:border-accent-main/50 hover:text-text-primary"
          )}
        >
          All
        </button>

        {/* Tag filters */}
        {tagOptions.map((option) => {
          const Icon = option.icon;
          const isActive = tagFilters.includes(option.tag);
          return (
            <button
              key={option.tag}
              onClick={() => toggleTagFilter(option.tag)}
              className={cn(
                "flex items-center gap-1.5 px-3 py-1.5 rounded-lg border text-xs font-medium transition-all",
                isActive
                  ? `bg-accent-main/20 border-accent-main ${option.color}`
                  : `bg-bg-surface border-border-main text-text-muted hover:border-accent-main/50 hover:text-text-primary`
              )}
            >
              <Icon size={14} className={isActive ? option.color : ""} />
              {option.label}
            </button>
          );
        })}

        {/* Has Notes */}
        <button
          onClick={() => setShowOnlyWithNotes(!showOnlyWithNotes)}
          className={cn(
            "flex items-center gap-1.5 px-3 py-1.5 rounded-lg border text-xs font-medium transition-all",
            showOnlyWithNotes
              ? "bg-accent-main/20 border-accent-main text-accent-main"
              : "bg-bg-surface border-border-main text-text-muted hover:border-accent-main/50 hover:text-text-primary"
          )}
        >
          <StickyNote size={14} />
          Has Notes
        </button>
      </div>

      {/* Count */}
      {hasActiveFilters && (
        <div className="text-xs text-text-muted">
          Showing <span className="font-bold text-accent-main">{filteredCount}</span> of{" "}
          <span className="font-bold">{totalCount}</span> trades
        </div>
      )}
    </div>
  );
};
