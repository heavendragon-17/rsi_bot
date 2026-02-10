import React from "react";
import { Edit2, X, Star, AlertTriangle, BookOpen, Lightbulb, Clover, Skull } from "lucide-react";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "../ui/popover";
import { Button } from "../ui/button";
import { TradeAnnotation, TradeTag } from "../../stores/exportStore";

interface NotePopoverProps {
  annotation: TradeAnnotation;
  onEdit: () => void;
  onClose: () => void;
  children: React.ReactNode;
}

export const NotePopover: React.FC<NotePopoverProps> = ({
  annotation,
  onEdit,
  onClose,
  children,
}) => {
  const tagIcons: Record<TradeTag, any> = {
    star: Star,
    review: AlertTriangle,
    learning: BookOpen,
    idea: Lightbulb,
    lucky: Clover,
    unlucky: Skull,
  };

  const tagColors: Record<TradeTag, string> = {
    star: "text-yellow-400",
    review: "text-orange-400",
    learning: "text-blue-400",
    idea: "text-purple-400",
    lucky: "text-green-400",
    unlucky: "text-red-400",
  };

  const formatDate = (isoString: string) => {
    const date = new Date(isoString);
    return date.toLocaleString("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
      hour: "numeric",
      minute: "2-digit",
    });
  };

  return (
    <Popover>
      <PopoverTrigger asChild>{children}</PopoverTrigger>
      <PopoverContent
        className="w-96 bg-bg-surface border-border-main"
        align="start"
      >
        <div className="space-y-3">
          {/* Header */}
          <div className="flex items-center justify-between pb-2 border-b border-border-main">
            <h3 className="text-sm font-semibold text-text-primary">
              TRADE #{annotation.tradeId} NOTE
            </h3>
            <div className="flex gap-1">
              <Button
                variant="ghost"
                size="sm"
                onClick={onEdit}
                className="h-7 w-7 p-0"
              >
                <Edit2 size={14} />
              </Button>
              <Button
                variant="ghost"
                size="sm"
                onClick={onClose}
                className="h-7 w-7 p-0"
              >
                <X size={14} />
              </Button>
            </div>
          </div>

          {/* Tags */}
          {annotation.tags.length > 0 && (
            <div className="flex gap-2">
              {annotation.tags.map((tag) => {
                const Icon = tagIcons[tag];
                const color = tagColors[tag];
                return (
                  <div
                    key={tag}
                    className="flex items-center gap-1 text-xs"
                  >
                    <Icon size={16} className={color} />
                  </div>
                );
              })}
            </div>
          )}

          {/* Note Content */}
          {annotation.note && (
            <div className="text-sm text-text-primary whitespace-pre-wrap leading-relaxed">
              {annotation.note}
            </div>
          )}

          {!annotation.note && (
            <div className="text-sm text-text-muted italic">
              No note added. Click Edit to add one.
            </div>
          )}

          {/* Timestamp */}
          <div className="pt-2 border-t border-border-main text-xs text-text-muted">
            Added: {formatDate(annotation.createdAt)}
            {annotation.updatedAt !== annotation.createdAt && (
              <> • Updated: {formatDate(annotation.updatedAt)}</>
            )}
          </div>
        </div>
      </PopoverContent>
    </Popover>
  );
};
