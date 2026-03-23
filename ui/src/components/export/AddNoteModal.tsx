import React, { useState, useEffect } from "react";
import { X, Star, AlertTriangle, BookOpen, Lightbulb, Clover, Skull } from "lucide-react";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "../ui/dialog";
import { Button } from "../ui/button";
import { Textarea } from "../ui/textarea";
import { useExportStore, TradeTag } from "../../stores/exportStore";
import { Trade } from "../../stores/resultsStore";
import { cn } from "../../lib/utils";
import { toast } from "sonner";

interface AddNoteModalProps {
  trade: Trade;
  onClose: () => void;
}

export const AddNoteModal: React.FC<AddNoteModalProps> = ({ trade, onClose }) => {
  const { annotations, addAnnotation, updateAnnotation } = useExportStore();

  const existingAnnotation = annotations[trade.id];
  const [note, setNote] = useState(existingAnnotation?.note || "");
  const [selectedTags, setSelectedTags] = useState<TradeTag[]>(
    existingAnnotation?.tags || []
  );

  const tagOptions: { tag: TradeTag; icon: any; label: string; color: string }[] = [
    { tag: "star", icon: Star, label: "Star", color: "text-yellow-400" },
    { tag: "review", icon: AlertTriangle, label: "Review", color: "text-orange-400" },
    { tag: "learning", icon: BookOpen, label: "Learning", color: "text-blue-400" },
    { tag: "idea", icon: Lightbulb, label: "Idea", color: "text-purple-400" },
    { tag: "lucky", icon: Clover, label: "Lucky", color: "text-green-400" },
    { tag: "unlucky", icon: Skull, label: "Unlucky", color: "text-red-400" },
  ];

  const toggleTag = (tag: TradeTag) => {
    setSelectedTags((prev) =>
      prev.includes(tag) ? prev.filter((t) => t !== tag) : [...prev, tag]
    );
  };

  const handleSave = () => {
    if (existingAnnotation) {
      updateAnnotation(trade.id, note, selectedTags);
      toast.success("Note updated successfully!");
    } else {
      addAnnotation(trade.id, note, selectedTags);
      toast.success("Note added successfully!");
    }
    onClose();
  };

  const duration = calculateDuration(trade.entryTime, trade.exitTime);
  const pnlPct = ((trade.pnl / trade.entryPrice) * 100).toFixed(2);

  return (
    <Dialog open={true} onOpenChange={onClose}>
      <DialogContent className="max-w-2xl bg-bg-surface border-border-main">
        <DialogHeader>
          <DialogTitle className="flex items-center justify-between">
            <span>
              {existingAnnotation ? "Edit" : "Add"} Note: Trade #{trade.id}
            </span>
          </DialogTitle>
        </DialogHeader>

        <div className="space-y-6 py-4">
          {/* Trade Summary */}
          <div className="space-y-2">
            <h3 className="text-sm font-semibold text-text-primary uppercase tracking-wider">
              TRADE SUMMARY
            </h3>
            <div className="p-4 border border-border-main rounded-lg bg-bg-elevated space-y-2">
              <div className="flex items-center justify-between text-sm">
                <span className="text-text-muted">Entry:</span>
                <span className="text-text-primary font-mono">
                  {trade.entryTime} @ ${trade.entryPrice.toFixed(4)}
                </span>
              </div>
              <div className="flex items-center justify-between text-sm">
                <span className="text-text-muted">Exit:</span>
                <span className="text-text-primary font-mono">
                  {trade.exitTime} @ ${trade.exitPrice.toFixed(4)}
                </span>
              </div>
              <div className="flex items-center justify-between text-sm">
                <span className="text-text-muted">PnL:</span>
                <span
                  className={cn(
                    "font-bold font-mono",
                    trade.pnl >= 0 ? "text-success" : "text-danger"
                  )}
                >
                  {trade.pnl >= 0 ? "+" : ""}${trade.pnl.toFixed(2)} ({trade.pnl >= 0 ? "+" : ""}
                  {pnlPct}%)
                </span>
              </div>
              <div className="flex items-center justify-between text-sm">
                <span className="text-text-muted">Duration:</span>
                <span className="text-text-primary font-mono">{duration}</span>
              </div>
            </div>
          </div>

          {/* Note Input */}
          <div className="space-y-2">
            <h3 className="text-sm font-semibold text-text-primary uppercase tracking-wider">
              YOUR NOTE
            </h3>
            <Textarea
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="Add your observations, lessons learned, or any other notes about this trade..."
              className="min-h-[150px] bg-bg-elevated border-border-main text-text-primary resize-none"
            />
          </div>

          {/* Tags */}
          <div className="space-y-2">
            <h3 className="text-sm font-semibold text-text-primary uppercase tracking-wider">
              TAGS
            </h3>
            <div className="flex flex-wrap gap-2">
              {tagOptions.map((option) => {
                const Icon = option.icon;
                const isSelected = selectedTags.includes(option.tag);
                return (
                  <button
                    key={option.tag}
                    onClick={() => toggleTag(option.tag)}
                    className={cn(
                      "flex items-center gap-2 px-3 py-2 rounded-lg border transition-all",
                      isSelected
                        ? "bg-accent-main/20 border-accent-main text-accent-main"
                        : "bg-bg-elevated border-border-main text-text-muted hover:border-accent-main/50 hover:text-text-primary"
                    )}
                  >
                    <Icon
                      size={16}
                      className={isSelected ? option.color : ""}
                    />
                    <span className="text-sm font-medium">{option.label}</span>
                    {isSelected && <span className="text-lg">✓</span>}
                  </button>
                );
              })}
            </div>
          </div>

          {/* Actions */}
          <div className="flex justify-between pt-4">
            <Button variant="outline" onClick={onClose}>
              Cancel
            </Button>
            <Button onClick={handleSave}>Save Note</Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
};

function calculateDuration(entryTime: string, exitTime: string): string {
  try {
    const entry = new Date(entryTime);
    const exit = new Date(exitTime);
    const diffMs = exit.getTime() - entry.getTime();
    const diffHours = Math.floor(diffMs / (1000 * 60 * 60));
    const diffDays = Math.floor(diffHours / 24);
    const remainingHours = diffHours % 24;

    if (diffDays > 0) {
      return `${diffDays} day${diffDays > 1 ? "s" : ""} ${remainingHours} hour${
        remainingHours !== 1 ? "s" : ""
      }`;
    }
    return `${diffHours} hour${diffHours !== 1 ? "s" : ""}`;
  } catch {
    return "Unknown";
  }
}
