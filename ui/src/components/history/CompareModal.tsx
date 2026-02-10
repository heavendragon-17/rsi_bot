import React from "react";
import { useHistoryStore } from "../../stores/historyStore";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "../ui/dialog";
import { Button } from "../ui/button";
import { ParameterDiff } from "./ParameterDiff";
import { TrendingUp, TrendingDown, X } from "lucide-react";
import { cn } from "../../lib/utils";

export const CompareModal: React.FC = () => {
  const { compareModalOpen, compareRuns, closeCompareModal, loadRun } = useHistoryStore();

  if (!compareRuns) return null;

  const [run1, run2] = compareRuns;

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

  // Determine winner
  const winner =
    run2.netPnL > run1.netPnL
      ? `Run #${run2.runNumber}`
      : run1.netPnL > run2.netPnL
      ? `Run #${run1.runNumber}`
      : "Tie";

  const pnlDiff = run2.netPnL - run1.netPnL;

  return (
    <Dialog open={compareModalOpen} onOpenChange={closeCompareModal}>
      <DialogContent className="max-w-5xl bg-bg-secondary border-border-main">
        <DialogHeader>
          <div className="flex items-center justify-between">
            <DialogTitle className="text-xl font-semibold text-text-primary flex items-center gap-2">
              <span className="text-2xl">⚖️</span>
              Compare Runs: #{run1.runNumber} vs #{run2.runNumber}
            </DialogTitle>
            <Button
              variant="ghost"
              size="sm"
              onClick={closeCompareModal}
              className="h-8 w-8 p-0"
            >
              <X size={16} />
            </Button>
          </div>
        </DialogHeader>

        <div className="space-y-6 max-h-[70vh] overflow-y-auto pr-2 custom-scrollbar">
          {/* Parameter Diff */}
          <ParameterDiff run1={run1} run2={run2} />

          {/* Results Comparison */}
          <div className="space-y-3">
            <div className="flex items-center gap-2">
              <span className="text-lg">📊</span>
              <h3 className="text-base font-semibold text-text-primary">Results Comparison</h3>
            </div>

            <div className="grid grid-cols-2 gap-4">
              {/* Run 1 Results */}
              <div className="p-4 bg-bg-elevated border border-border-main rounded-lg space-y-3">
                <div className="flex items-center justify-between border-b border-border-main/50 pb-2">
                  <h4 className="font-semibold text-text-primary">Run #{run1.runNumber}</h4>
                  <span className="text-xs text-text-muted px-2 py-0.5 bg-bg-surface rounded">
                    {run1.strategyName}
                  </span>
                </div>

                <div className="space-y-2">
                  <MetricRow
                    label="Net PnL"
                    value={formatPnL(run1.netPnL)}
                    color={run1.netPnL >= 0 ? "success" : "danger"}
                    icon={run1.netPnL >= 0 ? TrendingUp : TrendingDown}
                  />
                  <MetricRow label="Win Rate" value={`${run1.winRate.toFixed(1)}%`} />
                  <MetricRow label="Profit Factor" value={run1.profitFactor.toFixed(2)} />
                  <MetricRow label="Max Drawdown" value={`${run1.maxDrawdownPct.toFixed(1)}%`} />
                  <MetricRow label="Sharpe Ratio" value={run1.sharpeRatio.toFixed(2)} />
                  <MetricRow label="Total Trades" value={run1.tradeCount.toString()} />
                </div>
              </div>

              {/* Run 2 Results */}
              <div className="p-4 bg-bg-elevated border border-border-main rounded-lg space-y-3">
                <div className="flex items-center justify-between border-b border-border-main/50 pb-2">
                  <h4 className="font-semibold text-text-primary">Run #{run2.runNumber}</h4>
                  <span className="text-xs text-text-muted px-2 py-0.5 bg-bg-surface rounded">
                    {run2.strategyName}
                  </span>
                </div>

                <div className="space-y-2">
                  <MetricRow
                    label="Net PnL"
                    value={formatPnL(run2.netPnL)}
                    color={run2.netPnL >= 0 ? "success" : "danger"}
                    icon={run2.netPnL >= 0 ? TrendingUp : TrendingDown}
                  />
                  <MetricRow label="Win Rate" value={`${run2.winRate.toFixed(1)}%`} />
                  <MetricRow label="Profit Factor" value={run2.profitFactor.toFixed(2)} />
                  <MetricRow label="Max Drawdown" value={`${run2.maxDrawdownPct.toFixed(1)}%`} />
                  <MetricRow label="Sharpe Ratio" value={run2.sharpeRatio.toFixed(2)} />
                  <MetricRow label="Total Trades" value={run2.tradeCount.toString()} />
                </div>
              </div>
            </div>

            {/* Winner Banner */}
            <div
              className={cn(
                "p-4 rounded-lg border",
                pnlDiff === 0
                  ? "bg-bg-elevated border-border-main"
                  : pnlDiff > 0
                  ? "bg-success/5 border-success/30"
                  : "bg-danger/5 border-danger/30"
              )}
            >
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm font-medium text-text-primary">
                    {pnlDiff === 0 ? "Performance Equal" : `Winner: ${winner}`}
                  </p>
                  {pnlDiff !== 0 && (
                    <p className="text-xs text-text-muted mt-0.5">
                      {Math.abs(pnlDiff) > 0 &&
                        `${formatPnL(Math.abs(pnlDiff))} ${pnlDiff > 0 ? "better" : "worse"}`}
                    </p>
                  )}
                </div>
                {pnlDiff > 0 ? (
                  <TrendingUp className="text-success" size={20} />
                ) : pnlDiff < 0 ? (
                  <TrendingDown className="text-danger" size={20} />
                ) : null}
              </div>
            </div>
          </div>
        </div>

        {/* Footer Actions */}
        <div className="flex items-center justify-between pt-4 border-t border-border-main">
          <Button variant="outline" onClick={closeCompareModal}>
            Close
          </Button>
          <div className="flex gap-2">
            <Button
              variant="outline"
              onClick={() => {
                loadRun(run1.id);
                closeCompareModal();
              }}
            >
              Restore Run #{run1.runNumber} Settings
            </Button>
            <Button
              onClick={() => {
                loadRun(run2.id);
                closeCompareModal();
              }}
              className="bg-accent-main hover:bg-accent-hover text-white"
            >
              Restore Run #{run2.runNumber} Settings
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
};

// Helper component for metric rows
interface MetricRowProps {
  label: string;
  value: string;
  color?: "success" | "danger";
  icon?: React.ElementType;
}

const MetricRow: React.FC<MetricRowProps> = ({ label, value, color, icon: Icon }) => {
  return (
    <div className="flex items-center justify-between text-sm">
      <span className="text-text-secondary">{label}</span>
      <div className="flex items-center gap-1.5">
        {Icon && (
          <Icon
            size={14}
            className={cn(color === "success" && "text-success", color === "danger" && "text-danger")}
          />
        )}
        <span
          className={cn(
            "font-mono font-medium",
            color === "success" && "text-success",
            color === "danger" && "text-danger",
            !color && "text-text-primary"
          )}
        >
          {value}
        </span>
      </div>
    </div>
  );
};
