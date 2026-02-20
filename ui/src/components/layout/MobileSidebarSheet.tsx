// @ts-nocheck
import React from "react";
import { useBacktestStore } from "../../stores/backtestStore";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from "../ui/sheet";
import { cn } from "../../lib/utils";
import {
  Settings,
  Play,
  Layers,
  RotateCcw,
  ChevronRight,
  Code,
} from "lucide-react";
import { CollapsibleSection } from "../ui/CollapsibleSection";
import { ValidatedInput } from "../ui/ValidatedInput";
import { RunButton } from "./RunButton";
import { validateParam } from "../../lib/validation";
import { DateRangeSection } from "../date-controls/DateRangeSection";
import { useDataPrepStore } from "../../stores/dataPrepStore";
import { checkDataStatus } from "../../lib/data-utils";

/**
 * Mobile Sidebar Sheet
 * Displays on mobile/tablet when user taps menu icon
 * Swipeable bottom sheet with full configuration
 */
export const MobileSidebarSheet: React.FC = () => {
  const {
    isSidebarOpen,
    setSidebarOpen,
    mode,
    setMode,
    symbol,
    setSymbol,
    strategy,
    setStrategy,
    timeframe,
    setTimeframe,
    params,
    setParam,
    resetParams,
    capital,
    setCapital,
    leverage,
    setLeverage,
    riskPercent,
    setRiskPercent,
    isRunning,
    runBacktest,
    startDate,
    endDate,
  } = useBacktestStore();

  const [isMobile, setIsMobile] = React.useState(false);

  React.useEffect(() => {
    const checkIsMobile = () => setIsMobile(window.innerWidth < 1024);
    checkIsMobile();
    window.addEventListener("resize", checkIsMobile);
    return () => window.removeEventListener("resize", checkIsMobile);
  }, []);

  const {
    openModal,
    setPrepState,
    setSymbols,
    reset: resetPrep,
  } = useDataPrepStore();

  const executeRun = async () => {
    // backtestStore.runBacktest() handles API call, SSE, results, and history (server-side).
    await runBacktest();
    setSidebarOpen(false);
  };

  const handleRunRequest = async () => {
    if (mode === "pine") return;

    let isValid = true;
    Object.entries(params).forEach(([k, v]) => {
      if (!validateParam(k, v.toString()).isValid) isValid = false;
    });
    if (!validateParam("capital", capital).isValid) isValid = false;
    if (!validateParam("leverage", leverage).isValid) isValid = false;
    if (!validateParam("risk_percent", riskPercent).isValid) isValid = false;

    if (!isValid) return;

    resetPrep();
    const startTime = Date.now();

    const symbolsToCheck =
      mode === "batch"
        ? [
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
          ]
        : [symbol];

    try {
      const { allFresh, symbolStatuses } = await checkDataStatus(
        symbolsToCheck,
        timeframe,
        startDate,
        endDate
      );

      const elapsedTime = Date.now() - startTime;
      setSymbols(symbolStatuses);

      if (allFresh && elapsedTime < 500) {
        executeRun();
      } else if (allFresh) {
        setPrepState("ready");
        openModal();
      } else {
        setPrepState("downloading");
        openModal();
      }
    } catch (e) {
      executeRun();
    }
  };

  if (!isMobile) return null;

  return (
    <Sheet open={isSidebarOpen} onOpenChange={setSidebarOpen}>
      <SheetContent side="bottom" className="h-[85vh] p-0 lg:hidden">
        <SheetHeader className="p-4 border-b border-border-main">
          <SheetTitle>Configuration</SheetTitle>
          <SheetDescription>Adjust your backtest settings</SheetDescription>
        </SheetHeader>

        <div className="overflow-y-auto h-[calc(100%-140px)] custom-scrollbar p-4">
          {/* Mode Selection */}
          <CollapsibleSection title="Mode" defaultOpen={true}>
            <div className="grid grid-cols-3 gap-2 bg-bg-elevated p-1 rounded-lg">
              <button
                onClick={() => setMode("single")}
                className={cn(
                  "flex-1 py-2 text-xs font-medium rounded-md transition-all",
                  mode === "single"
                    ? "bg-bg-secondary text-text-primary shadow-sm"
                    : "text-text-secondary hover:text-text-primary"
                )}
              >
                Single
              </button>
              <button
                onClick={() => setMode("batch")}
                className={cn(
                  "flex-1 py-2 text-xs font-medium rounded-md transition-all",
                  mode === "batch"
                    ? "bg-bg-secondary text-text-primary shadow-sm"
                    : "text-text-secondary hover:text-text-primary"
                )}
              >
                Portfolio
              </button>
              <button
                onClick={() => setMode("pine")}
                className={cn(
                  "flex-1 py-2 text-xs font-medium rounded-md transition-all flex items-center justify-center gap-1",
                  mode === "pine"
                    ? "bg-bg-secondary text-accent-main shadow-sm"
                    : "text-text-secondary hover:text-text-primary"
                )}
              >
                <Code size={12} />
                Pine
              </button>
            </div>
          </CollapsibleSection>

          {mode !== "pine" && (
            <>
              {/* Symbol & Timeframe */}
              <CollapsibleSection title="Asset Config">
                <div className="space-y-3">
                  {mode === "single" ? (
                    <div>
                      <label className="text-xs font-medium text-text-secondary mb-1.5 block">
                        Symbol
                      </label>
                      <div className="relative">
                        <select
                          value={symbol}
                          onChange={(e) => setSymbol(e.target.value)}
                          className="w-full appearance-none bg-input/50 border border-border-main rounded-md px-3 py-3 text-sm text-text-primary focus:outline-none focus:ring-1 focus:ring-accent-main/50"
                        >
                          <option value="BTC/USDT">BTC/USDT</option>
                          <option value="ETH/USDT">ETH/USDT</option>
                          <option value="SOL/USDT">SOL/USDT</option>
                        </select>
                        <ChevronRight
                          className="absolute right-3 top-1/2 -translate-y-1/2 rotate-90 text-text-muted pointer-events-none"
                          size={14}
                        />
                      </div>
                    </div>
                  ) : (
                    <div>
                      <label className="text-xs font-medium text-text-secondary mb-1.5 block">
                        Portfolio Config
                      </label>
                      <div className="p-3 bg-bg-elevated rounded border border-border-main text-xs text-text-secondary">
                        <div className="flex items-center gap-2 mb-1">
                          <Layers size={14} className="text-accent-main" />
                          <span className="font-semibold text-text-primary">
                            12 Assets Selected
                          </span>
                        </div>
                        <div className="opacity-75">
                          BTC, ETH, SOL, BNB, ADA...
                        </div>
                      </div>
                    </div>
                  )}

                  <div>
                    <label className="text-xs font-medium text-text-secondary mb-1.5 block">
                      Timeframe
                    </label>
                    <div className="grid grid-cols-4 gap-2">
                      {["15m", "1h", "4h", "1d"].map((tf) => (
                        <button
                          key={tf}
                          onClick={() => setTimeframe(tf)}
                          className={cn(
                            "py-2 border rounded-md text-sm font-medium transition-colors min-h-[44px]",
                            timeframe === tf
                              ? "bg-accent-main/10 border-accent-main text-accent-main"
                              : "border-border-main text-text-secondary hover:border-text-muted"
                          )}
                        >
                          {tf}
                        </button>
                      ))}
                    </div>
                  </div>
                </div>
              </CollapsibleSection>

              {/* Date Controls */}
              <CollapsibleSection title="Date Range">
                <DateRangeSection />
              </CollapsibleSection>

              {/* Strategy Selection */}
              <CollapsibleSection title="Strategy">
                <div className="relative">
                  <select
                    value={strategy}
                    onChange={(e) => setStrategy(e.target.value)}
                    className="w-full appearance-none bg-input/50 border border-border-main rounded-md px-3 py-3 text-sm text-text-primary focus:outline-none focus:ring-1 focus:ring-accent-main/50"
                  >
                    <option value="rsi_no_retest">RSI No Retest</option>
                    <option value="macd_cross">MACD Crossover</option>
                    <option value="bollinger_breakout">
                      Bollinger Breakout
                    </option>
                  </select>
                  <Settings
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-text-muted pointer-events-none"
                    size={14}
                  />
                </div>
              </CollapsibleSection>

              {/* Parameters */}
              <CollapsibleSection
                title="Parameters"
                headerAction={
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      resetParams();
                    }}
                    className="p-1 hover:bg-bg-elevated rounded text-text-muted hover:text-text-primary transition-colors"
                    title="Reset to Defaults"
                  >
                    <RotateCcw size={12} />
                  </button>
                }
              >
                <div className="space-y-3">
                  <ValidatedInput
                    label="RSI Period"
                    paramKey="rsi_period"
                    value={params.rsi_period}
                    onChangeValue={(v) => setParam("rsi_period", v)}
                  />
                  <ValidatedInput
                    label="EMA Fast"
                    paramKey="ema_fast"
                    value={params.ema_fast}
                    onChangeValue={(v) => setParam("ema_fast", v)}
                  />
                  <ValidatedInput
                    label="EMA Slow"
                    paramKey="ema_slow"
                    value={params.ema_slow}
                    onChangeValue={(v) => setParam("ema_slow", v)}
                  />
                  <ValidatedInput
                    label="TP1 Risk Ratio"
                    paramKey="tp1_rr"
                    value={params.tp1_rr}
                    onChangeValue={(v) => setParam("tp1_rr", v)}
                    suffix="R"
                  />
                  <ValidatedInput
                    label="SL Buffer"
                    paramKey="sl_buffer_pct"
                    value={params.sl_buffer_pct}
                    onChangeValue={(v) => setParam("sl_buffer_pct", v)}
                    suffix="%"
                  />
                </div>
              </CollapsibleSection>

              {/* Risk Settings */}
              <CollapsibleSection title="Risk Management">
                <div className="space-y-3">
                  <ValidatedInput
                    label="Initial Capital"
                    paramKey="capital"
                    value={capital}
                    onChangeValue={setCapital}
                    suffix="$"
                  />
                  <div className="grid grid-cols-2 gap-3">
                    <ValidatedInput
                      label="Leverage"
                      paramKey="leverage"
                      value={leverage}
                      onChangeValue={setLeverage}
                      suffix="x"
                    />
                    <ValidatedInput
                      label="Risk Per Trade"
                      paramKey="risk_percent"
                      value={riskPercent}
                      onChangeValue={setRiskPercent}
                      suffix="%"
                    />
                  </div>
                </div>
              </CollapsibleSection>
            </>
          )}

          {mode === "pine" && (
            <div className="p-4 text-xs text-text-muted italic">
              Use the Pine Script Translator to import strategies from
              TradingView.
              <br />
              <br />
              Once saved, they will appear in your Strategy list.
            </div>
          )}
        </div>

        {/* Sticky Footer with Run Button */}
        {mode !== "pine" && (
          <div className="absolute bottom-0 left-0 right-0 p-4 border-t border-border-main bg-bg-surface/95 backdrop-blur-md">
            <RunButton onClick={handleRunRequest} />
          </div>
        )}
      </SheetContent>
    </Sheet>
  );
};
