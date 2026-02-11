import React, { useState } from "react";
import {
  Wrench,
  Trash2,
  Database,
  Play,
  History,
  Sparkles,
  LayoutGrid,
  Activity,
  TrendingUp,
  BarChart2,
} from "lucide-react";
import { Button } from "../ui/button";
import { Card } from "../ui/card";
import { Popover, PopoverContent, PopoverTrigger } from "../ui/popover";
import { useResultsStore } from "../../stores/resultsStore";
import { useBatchResultsStore } from "../../stores/batchResultsStore";
import { useGridSearchStore } from "../../stores/gridSearchStore";
import { useWalkForwardStore } from "../../stores/walkForwardStore";
import { useSensitivityStore } from "../../stores/sensitivityStore";
import { useHistoryStore } from "../../stores/historyStore";
import { useBacktestStore } from "../../stores/backtestStore";
import { cn } from "../../lib/utils";
import { toast } from "sonner";

export const DevTools: React.FC = () => {
  const [isOpen, setIsOpen] = useState(false);

  // Stores
  const { generateMockResults, clearResults } = useResultsStore();
  const { generateMockBatchResults, clearBatchResults } =
    useBatchResultsStore();
  const { runGridSearch, reset: resetGrid } = useGridSearchStore();
  const { runWalkForward, reset: resetWalk } = useWalkForwardStore();
  const { runSensitivityAnalysis, reset: resetSens } = useSensitivityStore();
  const { addRun, clearAllHistory } = useHistoryStore();
  const { setMode } = useBacktestStore();

  const handleGenerateAll = async () => {
    // 1. Single Results
    generateMockResults(10000);
    toast.success("Result Dashboard populated");

    // 2. Batch Results
    const batchSymbols = [
      "BTC/USDT",
      "ETH/USDT",
      "SOL/USDT",
      "BNB/USDT",
      "ADA/USDT",
      "XRP/USDT",
      "DOGE/USDT",
      "DOT/USDT",
      "MATIC/USDT",
      "LTC/USDT",
      "UNI/USDT",
      "LINK/USDT",
    ];
    generateMockBatchResults(50000, batchSymbols);
    toast.success("Portfolio Dashboard populated");

    // 3. Grid Search (Async trigger)
    try {
      resetGrid();
      setTimeout(() => {
        runGridSearch();
        toast.info("Grid Search started in background...");
      }, 100);
    } catch (e) {
      console.error(e);
    }

    // 4. Walk Forward
    try {
      resetWalk();
      setTimeout(() => {
        runWalkForward();
        toast.info("Walk Forward started in background...");
      }, 300);
    } catch (e) {
      console.error(e);
    }

    // 5. Sensitivity
    try {
      resetSens();
      setTimeout(() => {
        runSensitivityAnalysis();
        toast.info("Sensitivity Analysis started in background...");
      }, 500);
    } catch (e) {
      console.error(e);
    }
  };

  const handleInjectHistory = () => {
    const strategies = [
      "RSI No Retest",
      "MACD Cross",
      "Bollinger Breakout",
      "Mean Reversion",
      "Trend Follower",
    ];
    const symbols = [
      "BTC/USDT",
      "ETH/USDT",
      "SOL/USDT",
      "BNB/USDT",
      "ADA/USDT",
    ];

    // Add 15 runs
    for (let i = 0; i < 15; i++) {
      const isWin = Math.random() > 0.45;
      const pnl = Math.random() * 2000 * (isWin ? 1 : -0.6); // Slightly biased towards profit/loss ratio

      addRun({
        strategyName: strategies[Math.floor(Math.random() * strategies.length)],
        strategyVersion: "v1.0",
        symbol: symbols[Math.floor(Math.random() * symbols.length)],
        isBatch: Math.random() > 0.8, // 20% mock as batch
        parameters: {
          rsi_period: 14,
          capital: 10000,
          timeframe: "1h",
          riskPercent: 1,
          leverage: 1,
        },
        netPnL: parseFloat(pnl.toFixed(2)),
        netPnLPct: parseFloat((pnl / 100).toFixed(2)), // assuming 10k capital
        winRate: parseFloat((40 + Math.random() * 40).toFixed(1)),
        profitFactor: parseFloat((0.8 + Math.random() * 2).toFixed(2)),
        maxDrawdownPct: parseFloat((5 + Math.random() * 25).toFixed(2)),
        sharpeRatio: parseFloat((Math.random() * 3 - 0.5).toFixed(2)),
        tradeCount: 50 + Math.floor(Math.random() * 100),
      });
    }
    toast.success("Injected 15 historical runs");
  };

  const handleClearAll = () => {
    clearResults();
    clearBatchResults();
    resetGrid();
    resetWalk();
    resetSens();
    clearAllHistory();
    toast.info("All data cleared");
  };

  const navigateTo = (mode: any) => {
    setMode(mode);
    setIsOpen(false);
  };

  return (
    <Popover open={isOpen} onOpenChange={setIsOpen}>
      <PopoverTrigger asChild>
        <Button
          className="p-2 rounded-md text-text-secondary hover:text-text-primary hover:bg-bg-elevated transition-colors min-h-[44px] min-w-[44px] flex items-center justify-center"
          title="DevTools"
        >
          <Wrench size={18} />
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-80 p-0 border border-border-main bg-bg-surface/95 backdrop-blur-xl shadow-2xl mr-4">
        {/* Header */}
        <div className="flex items-center justify-between p-3 border-b border-border-main/50 bg-bg-elevated/50">
          <div className="flex items-center gap-2">
            <div className="w-6 h-6 rounded bg-accent-main/20 flex items-center justify-center">
              <Wrench className="w-3 h-3 text-accent-main" />
            </div>
            <h3 className="font-bold text-sm text-text-primary">DevTools</h3>
          </div>
        </div>

        {/* Content */}
        <div className="p-4 space-y-4">
          {/* Data Injection */}
          <div className="space-y-2">
            <label className="text-[10px] font-bold text-text-secondary uppercase tracking-wider">
              Mock Data Injection
            </label>
            <Button
              onClick={handleGenerateAll}
              className="w-full gap-2 bg-gradient-to-r from-accent-main to-accent-hover text-white border-none h-9 text-xs"
            >
              <Sparkles className="w-3 h-3" />
              Populate All Stores
            </Button>
            <Button
              onClick={handleInjectHistory}
              variant="outline"
              className="w-full gap-2 h-9 text-xs"
            >
              <History className="w-3 h-3" />
              Inject History (15 Runs)
            </Button>
          </div>

          {/* Quick Navigation */}
          <div className="space-y-2">
            <label className="text-[10px] font-bold text-text-secondary uppercase tracking-wider">
              Quick Navigation
            </label>
            <div className="grid grid-cols-3 gap-2">
              <NavButton
                label="Single"
                icon={Activity}
                onClick={() => navigateTo("single")}
              />
              <NavButton
                label="Portfolio"
                icon={LayoutGrid}
                onClick={() => navigateTo("batch")}
              />
              <NavButton
                label="History"
                icon={History}
                onClick={() => navigateTo("history")}
              />
              <NavButton
                label="Grid"
                icon={LayoutGrid}
                onClick={() => navigateTo("grid-search")}
              />
              <NavButton
                label="WalkFwd"
                icon={TrendingUp}
                onClick={() => navigateTo("walk-forward")}
              />
              <NavButton
                label="Sensit."
                icon={BarChart2}
                onClick={() => navigateTo("sensitivity")}
              />
            </div>
          </div>

          {/* Destructive Actions */}
          <div className="pt-3 border-t border-border-main/50">
            <Button
              onClick={handleClearAll}
              variant="destructive"
              className="w-full gap-2 h-8 text-xs opacity-90 hover:opacity-100"
            >
              <Trash2 className="w-3 h-3" />
              Reset All Data
            </Button>
          </div>
        </div>
      </PopoverContent>
    </Popover>
  );
};

// Helper for nav buttons
const NavButton = ({
  label,
  icon: Icon,
  onClick,
}: {
  label: string;
  icon: any;
  onClick: () => void;
}) => (
  <Button
    variant="outline"
    size="sm"
    className="text-[10px] h-8 flex flex-col gap-0 items-center justify-center px-1"
    onClick={onClick}
  >
    {label}
  </Button>
);
