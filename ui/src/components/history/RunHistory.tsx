import React from "react";
import { HistoryTable } from "./HistoryTable";
import { HistoryFilters } from "./HistoryFilters";
import { ComparePanel } from "./ComparePanel";
import { CompareModal } from "./CompareModal";
import { RestoreConfirmModal } from "./RestoreConfirmModal";
import { useHistoryStore } from "../../stores/historyStore";
import { Button } from "../ui/button";
import { Trash2 } from "lucide-react";
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

export const RunHistory: React.FC = () => {
  const { runs, deleteRuns } = useHistoryStore();

  return (
    <div className="h-full flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between px-6 py-4 border-b border-border-main/50">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-lg bg-accent-main/10 flex items-center justify-center">
            <span className="text-accent-main text-xl">📜</span>
          </div>
          <div>
            <h1 className="text-xl font-semibold text-text-primary">Run History</h1>
            <p className="text-xs text-text-muted">
              {runs.length} total {runs.length === 1 ? "run" : "runs"}
            </p>
          </div>
        </div>

        <div className="flex gap-2">
          {runs.length > 0 && (
            <AlertDialog>
              <AlertDialogTrigger asChild>
                <Button variant="outline" size="sm" className="gap-2">
                  <Trash2 size={14} />
                  Clear All History
                </Button>
              </AlertDialogTrigger>
              <AlertDialogContent className="bg-bg-secondary border-border-main">
                <AlertDialogHeader>
                  <AlertDialogTitle className="text-text-primary">
                    Clear All History?
                  </AlertDialogTitle>
                  <AlertDialogDescription className="text-text-secondary">
                    This will permanently delete all {runs.length} run{runs.length !== 1 ? "s" : ""}{" "}
                    from history. This action cannot be undone.
                  </AlertDialogDescription>
                </AlertDialogHeader>
                <AlertDialogFooter>
                  <AlertDialogCancel className="bg-bg-elevated text-text-primary border-border-main hover:bg-bg-elevated/80">
                    Cancel
                  </AlertDialogCancel>
                  <AlertDialogAction
                    onClick={() => deleteRuns(runs.map(r => r.id))}
                    className="bg-danger hover:bg-danger/90 text-white"
                  >
                    Delete All
                  </AlertDialogAction>
                </AlertDialogFooter>
              </AlertDialogContent>
            </AlertDialog>
          )}
        </div>
      </div>

      {/* Filters */}
      {runs.length > 0 && <HistoryFilters />}

      {/* Table */}
      <div className="flex-1 overflow-hidden">
        <HistoryTable />
      </div>

      {/* Compare Panel (sticky bottom) */}
      <ComparePanel />

      {/* Modals */}
      <CompareModal />
      <RestoreConfirmModal />
    </div>
  );
};