import React from "react";
import { useHistoryStore } from "../../stores/historyStore";
import { Button } from "../ui/button";
import { GitCompare, Eye, Trash2, Lightbulb } from "lucide-react";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "../ui/alert-dialog";

export const ComparePanel: React.FC = () => {
  const { selectedRunIds, compareSelected, loadRun, deleteRuns, runs, clearSelection } =
    useHistoryStore();

  const selectedCount = selectedRunIds.size;

  // Don't show panel if no runs selected
  if (selectedCount === 0) {
    return null;
  }

  const selectedRuns = Array.from(selectedRunIds)
    .map((id) => runs.find((r) => r.id === id))
    .filter((r) => r !== undefined);

  const canCompare = selectedCount === 2;
  const canLoad = selectedCount === 1;

  return (
    <div className="border-t border-border-main bg-bg-surface/80 backdrop-blur-sm px-6 py-4">
      <div className="flex items-center justify-between">
        {/* Selection Info */}
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-full bg-accent-main/20 flex items-center justify-center">
              <span className="text-sm font-semibold text-accent-main">{selectedCount}</span>
            </div>
            <div>
              <p className="text-sm font-medium text-text-primary">
                {selectedCount} run{selectedCount !== 1 ? "s" : ""} selected
              </p>
              <p className="text-xs text-text-muted">
                {canCompare
                  ? "Ready to compare"
                  : selectedCount === 1
                  ? "Select one more to compare"
                  : "Select exactly 2 runs to compare"}
              </p>
            </div>
          </div>

          {/* Tip */}
          {selectedCount < 2 && (
            <div className="flex items-center gap-2 ml-4 px-3 py-1.5 bg-accent-main/5 border border-accent-main/20 rounded-lg">
              <Lightbulb size={14} className="text-accent-main" />
              <span className="text-xs text-text-secondary">
                Select exactly 2 runs to compare parameter changes
              </span>
            </div>
          )}
        </div>

        {/* Actions */}
        <div className="flex items-center gap-2">
          {/* Load Run (single selection) */}
          {canLoad && (
            <Button
              onClick={() => loadRun(selectedRuns[0]!.id)}
              className="gap-2 bg-accent-main hover:bg-accent-hover text-white"
            >
              <Eye size={14} />
              Load Run #{selectedRuns[0]!.runNumber}
            </Button>
          )}

          {/* Compare (exactly 2 selected) */}
          <Button
            onClick={compareSelected}
            disabled={!canCompare}
            className="gap-2 bg-accent-main hover:bg-accent-hover text-white disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <GitCompare size={14} />
            Compare Selected
          </Button>

          {/* Delete Selected */}
          <AlertDialog>
            <AlertDialogTrigger asChild>
              <Button variant="outline" className="gap-2 border-danger/50 text-danger hover:bg-danger/10">
                <Trash2 size={14} />
                Delete Selected
              </Button>
            </AlertDialogTrigger>
            <AlertDialogContent className="bg-bg-secondary border-border-main">
              <AlertDialogHeader>
                <AlertDialogTitle className="text-text-primary">
                  Delete {selectedCount} Run{selectedCount !== 1 ? "s" : ""}?
                </AlertDialogTitle>
                <AlertDialogDescription className="text-text-secondary">
                  This will permanently delete the selected run{selectedCount !== 1 ? "s" : ""} from
                  history. This action cannot be undone.
                </AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel className="bg-bg-elevated text-text-primary border-border-main hover:bg-bg-elevated/80">
                  Cancel
                </AlertDialogCancel>
                <AlertDialogAction
                  onClick={() => {
                    deleteRuns(Array.from(selectedRunIds));
                    clearSelection();
                  }}
                  className="bg-danger hover:bg-danger/90 text-white"
                >
                  Delete
                </AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>

          {/* Clear Selection */}
          <Button
            variant="ghost"
            onClick={clearSelection}
            className="text-text-secondary hover:text-text-primary"
          >
            Clear
          </Button>
        </div>
      </div>
    </div>
  );
};
