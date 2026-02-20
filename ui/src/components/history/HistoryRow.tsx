import React from "react";
import { useHistoryStore, type HistoryRun } from "../../stores/historyStore";
import { Checkbox } from "../ui/checkbox";
import { Button } from "../ui/button";
import { Eye, Trash2, TrendingUp, TrendingDown, Layers } from "lucide-react";
import { cn } from "../../lib/utils";
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

interface HistoryRowProps {
  run: HistoryRun;
}

export const HistoryRow: React.FC<HistoryRowProps> = ({ run }) => {
  const { selectedRunIds, toggleRunSelection, loadRun, deleteRuns } = useHistoryStore();

  const isSelected = selectedRunIds.has(run.id);
  const isProfitable = run.netPnL > 0;

  // Format date/time
  const formatDateTime = (timestamp: string) => {
    const date = new Date(timestamp);
    return date.toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  };

  // Format PnL
  const formatPnL = (pnl: number) => {
    const formatted = Math.abs(pnl).toLocaleString("en-US", {
      style: "currency",
      currency: "USD",
      minimumFractionDigits: 0,
      maximumFractionDigits: 0,
    });
    return pnl >= 0 ? `+${formatted}` : `-${formatted}`;
  };

  return (
    <tr
      className={cn(
        "hover:bg-bg-elevated/50 transition-colors cursor-pointer group",
        isSelected && "bg-accent-main/5 border-l-2 border-l-accent-main"
      )}
      onClick={() => toggleRunSelection(run.id)}
    >
      {/* Checkbox */}
      <td className="px-4 py-3">
        <Checkbox
          checked={isSelected}
          onCheckedChange={() => toggleRunSelection(run.id)}
          onClick={(e) => e.stopPropagation()}
          className="border-border-main"
        />
      </td>

      {/* Run Number */}
      <td className="px-4 py-3">
        <span className="text-sm font-mono text-text-primary">#{run.runNumber}</span>
      </td>

      {/* Date/Time */}
      <td className="px-4 py-3">
        <span className="text-sm text-text-secondary">{formatDateTime(run.timestamp)}</span>
      </td>

      {/* Strategy */}
      <td className="px-4 py-3">
        <div className="flex flex-col">
          <span className="text-sm text-text-primary font-medium">{run.strategyName}</span>
          {run.strategyVersion && (
            <span className="text-xs text-text-muted">{run.strategyVersion}</span>
          )}
        </div>
      </td>

      {/* Symbol */}
      <td className="px-4 py-3">
        <div className="flex items-center gap-1.5">
          {run.isBatch && <Layers size={12} className="text-accent-main" />}
          <span className="text-sm text-text-primary font-mono">
            {run.isBatch ? "BATCH" : run.symbol}
          </span>
        </div>
      </td>

      {/* Net PnL */}
      <td className="px-4 py-3">
        <div className="flex items-center gap-1.5">
          {isProfitable ? (
            <TrendingUp size={14} className="text-success" />
          ) : (
            <TrendingDown size={14} className="text-danger" />
          )}
          <span
            className={cn(
              "text-sm font-semibold font-mono",
              isProfitable ? "text-success" : "text-danger"
            )}
          >
            {formatPnL(run.netPnL)}
          </span>
        </div>
      </td>

      {/* Win Rate */}
      <td className="px-4 py-3">
        <span className="text-sm text-text-secondary font-mono">
          {run.winRate.toFixed(1)}%
        </span>
      </td>

      {/* Actions */}
      <td className="px-4 py-3">
        <div
          className="flex items-center justify-end gap-1 opacity-0 group-hover:opacity-100 transition-opacity"
          onClick={(e) => e.stopPropagation()}
        >
          <Button
            variant="ghost"
            size="sm"
            onClick={() => loadRun(run.id)}
            className="h-7 px-2 hover:bg-bg-elevated"
          >
            <Eye size={14} className="text-text-secondary" />
          </Button>

          <AlertDialog>
            <AlertDialogTrigger asChild>
              <Button variant="ghost" size="sm" className="h-7 px-2 hover:bg-danger/10">
                <Trash2 size={14} className="text-danger" />
              </Button>
            </AlertDialogTrigger>
            <AlertDialogContent className="bg-bg-secondary border-border-main">
              <AlertDialogHeader>
                <AlertDialogTitle className="text-text-primary">Delete Run #{run.runNumber}?</AlertDialogTitle>
                <AlertDialogDescription className="text-text-secondary">
                  This will permanently delete this run from history. This action cannot be undone.
                </AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel className="bg-bg-elevated text-text-primary border-border-main hover:bg-bg-elevated/80">
                  Cancel
                </AlertDialogCancel>
                <AlertDialogAction
                  onClick={() => deleteRuns([run.id])}
                  className="bg-danger hover:bg-danger/90 text-white"
                >
                  Delete
                </AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>
        </div>
      </td>
    </tr>
  );
};
