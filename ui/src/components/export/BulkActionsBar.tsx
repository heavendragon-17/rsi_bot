import React from "react";
import { X, Tag, TagIcon } from "lucide-react";
import { useExportStore, TradeTag } from "../../stores/exportStore";
import { Button } from "../ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "../ui/dropdown-menu";
import { toast } from "sonner";

export const BulkActionsBar: React.FC = () => {
  const { selectedTradeIds, clearSelection, bulkAddTag, bulkRemoveTag } =
    useExportStore();

  if (selectedTradeIds.size === 0) return null;

  const tagOptions: { tag: TradeTag; label: string; emoji: string }[] = [
    { tag: "star", label: "Star", emoji: "🌟" },
    { tag: "review", label: "Review", emoji: "⚠️" },
    { tag: "learning", label: "Learning", emoji: "📚" },
    { tag: "idea", label: "Idea", emoji: "💡" },
    { tag: "lucky", label: "Lucky", emoji: "🍀" },
    { tag: "unlucky", label: "Unlucky", emoji: "💀" },
  ];

  const handleAddTag = (tag: TradeTag, label: string) => {
    bulkAddTag(tag);
    toast.success(`Added "${label}" tag to ${selectedTradeIds.size} trade(s)`);
  };

  const handleRemoveTag = (tag: TradeTag, label: string) => {
    bulkRemoveTag(tag);
    toast.success(`Removed "${label}" tag from ${selectedTradeIds.size} trade(s)`);
  };

  return (
    <div className="flex items-center justify-between px-4 py-3 bg-accent-main/10 border-b border-accent-main/30">
      <div className="flex items-center gap-3">
        <span className="text-sm font-medium text-accent-main">
          {selectedTradeIds.size} trade{selectedTradeIds.size > 1 ? "s" : ""} selected
        </span>
        
        {/* Add Tag Dropdown */}
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="outline" size="sm" className="gap-2">
              <Tag size={14} />
              Add Tag
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start">
            {tagOptions.map((option) => (
              <DropdownMenuItem
                key={option.tag}
                onClick={() => handleAddTag(option.tag, option.label)}
                className="cursor-pointer"
              >
                <span className="mr-2">{option.emoji}</span>
                {option.label}
              </DropdownMenuItem>
            ))}
          </DropdownMenuContent>
        </DropdownMenu>

        {/* Remove Tag Dropdown */}
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="outline" size="sm" className="gap-2">
              <TagIcon size={14} />
              Remove Tag
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start">
            {tagOptions.map((option) => (
              <DropdownMenuItem
                key={option.tag}
                onClick={() => handleRemoveTag(option.tag, option.label)}
                className="cursor-pointer"
              >
                <span className="mr-2">{option.emoji}</span>
                {option.label}
              </DropdownMenuItem>
            ))}
          </DropdownMenuContent>
        </DropdownMenu>
      </div>

      <Button
        variant="ghost"
        size="sm"
        onClick={clearSelection}
        className="gap-2"
      >
        <X size={14} />
        Clear Selection
      </Button>
    </div>
  );
};
