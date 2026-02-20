// @ts-nocheck
import React from "react";
import { useHistoryStore } from "../../stores/historyStore";
import { useBacktestStore } from "../../stores/backtestStore";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "../ui/dialog";
import { Button } from "../ui/button";
import { CheckCircle2 } from "lucide-react";

export const RestoreConfirmModal: React.FC = () => {
  const { restoreModalOpen, runToRestore, confirmRestore, cancelRestore } = useHistoryStore();
  const {
    setSymbol,
    setStrategy,
    setTimeframe,
    setParam,
    setCapital,
    setLeverage,
    setRiskPercent,
    setDateRange,
    setMode,
  } = useBacktestStore();

  if (!runToRestore) return null;

  const handleRestore = () => {
    const params = runToRestore.parameters;

    // Restore all parameters
    if (params.rsi_period !== undefined) setParam("rsi_period", params.rsi_period);
    if (params.ema_fast !== undefined) setParam("ema_fast", params.ema_fast);
    if (params.ema_slow !== undefined) setParam("ema_slow", params.ema_slow);
    if (params.tp1_rr !== undefined) setParam("tp1_rr", params.tp1_rr);
    if (params.tp2_rr !== undefined) setParam("tp2_rr", params.tp2_rr);
    if (params.sl_buffer_pct !== undefined) setParam("sl_buffer_pct", params.sl_buffer_pct);

    // Restore config
    if (params.capital !== undefined) setCapital(params.capital.toString());
    if (params.leverage !== undefined) setLeverage(params.leverage.toString());
    if (params.riskPercent !== undefined) setRiskPercent(params.riskPercent.toString());
    if (params.timeframe) setTimeframe(params.timeframe);

    // Restore symbol and strategy
    setSymbol(runToRestore.symbol);
    setStrategy(runToRestore.strategyName);

    // Restore dates if available
    if (params.startDate) {
      const start = new Date(params.startDate);
      const end = params.endDate ? new Date(params.endDate) : null;
      setDateRange(start, end);
    }

    // Switch to appropriate mode
    setMode(runToRestore.isBatch ? "batch" : "single");

    confirmRestore();
  };

  // Format value for display
  const formatValue = (val: any) => {
    if (val === null || val === undefined) return "—";
    if (typeof val === "number") return val.toString();
    if (val instanceof Date || typeof val === "string") {
      try {
        const date = new Date(val);
        if (!isNaN(date.getTime())) {
          return date.toLocaleDateString("en-US");
        }
      } catch {
        // Not a date
      }
    }
    return String(val);
  };

  const params = runToRestore.parameters;

  return (
    <Dialog open={restoreModalOpen} onOpenChange={cancelRestore}>
      <DialogContent className="max-w-lg bg-bg-secondary border-border-main">
        <DialogHeader>
          <DialogTitle className="text-xl font-semibold text-text-primary flex items-center gap-2">
            <span className="text-2xl">🔄</span>
            Restore Settings from Run #{runToRestore.runNumber}?
          </DialogTitle>
        </DialogHeader>

        <div className="space-y-4">
          <p className="text-sm text-text-secondary">
            This will update your current settings to match Run #{runToRestore.runNumber}:
          </p>

          {/* Settings Preview */}
          <div className="p-4 bg-bg-elevated border border-border-main rounded-lg space-y-2 max-h-[300px] overflow-y-auto custom-scrollbar">
            <SettingItem label="Strategy" value={runToRestore.strategyName} />
            <SettingItem label="Symbol" value={runToRestore.symbol} />
            <SettingItem label="Timeframe" value={formatValue(params.timeframe)} />

            {params.rsi_period !== undefined && (
              <SettingItem label="RSI Period" value={formatValue(params.rsi_period)} />
            )}
            {params.ema_fast !== undefined && (
              <SettingItem label="EMA Fast" value={formatValue(params.ema_fast)} />
            )}
            {params.ema_slow !== undefined && (
              <SettingItem label="EMA Slow" value={formatValue(params.ema_slow)} />
            )}
            {params.tp1_rr !== undefined && (
              <SettingItem label="Take Profit 1" value={formatValue(params.tp1_rr)} />
            )}
            {params.tp2_rr !== undefined && (
              <SettingItem label="Take Profit 2" value={formatValue(params.tp2_rr)} />
            )}
            {params.sl_buffer_pct !== undefined && (
              <SettingItem label="Stop Loss Buffer" value={`${formatValue(params.sl_buffer_pct)}%`} />
            )}
            {params.capital !== undefined && (
              <SettingItem label="Capital" value={`$${formatValue(params.capital)}`} />
            )}
            {params.leverage !== undefined && (
              <SettingItem label="Leverage" value={`${formatValue(params.leverage)}x`} />
            )}
            {params.riskPercent !== undefined && (
              <SettingItem label="Risk Per Trade" value={`${formatValue(params.riskPercent)}%`} />
            )}
            {params.startDate && (
              <SettingItem label="Start Date" value={formatValue(params.startDate)} />
            )}
            {params.endDate && (
              <SettingItem label="End Date" value={formatValue(params.endDate)} />
            )}
          </div>

          {/* Info banner */}
          <div className="flex items-start gap-2 p-3 bg-accent-main/5 border border-accent-main/20 rounded-lg">
            <CheckCircle2 size={16} className="text-accent-main mt-0.5 shrink-0" />
            <p className="text-xs text-text-secondary">
              Your current settings will be overwritten with these values. You can then run a new
              backtest or modify the settings further.
            </p>
          </div>
        </div>

        {/* Footer Actions */}
        <div className="flex items-center justify-end gap-2 pt-4 border-t border-border-main">
          <Button variant="outline" onClick={cancelRestore}>
            Cancel
          </Button>
          <Button
            onClick={handleRestore}
            className="bg-accent-main hover:bg-accent-hover text-white"
          >
            Restore Settings
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
};

// Helper component for setting items
interface SettingItemProps {
  label: string;
  value: string;
}

const SettingItem: React.FC<SettingItemProps> = ({ label, value }) => {
  return (
    <div className="flex items-center justify-between text-sm py-1">
      <span className="text-text-secondary">{label}:</span>
      <span className="text-text-primary font-mono font-medium">{value}</span>
    </div>
  );
};
