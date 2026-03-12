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
} from "lucide-react";
import { CollapsibleSection } from "../ui/CollapsibleSection";
import { ValidatedInput } from "../ui/ValidatedInput";
import { RunButton } from "./RunButton";
import { validateParam } from "../../lib/validation";
import { DateRangeSection } from "../date-controls/DateRangeSection";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../ui/select";
import { useDataPrepStore } from "../../stores/dataPrepStore";
import { checkDataStatus } from "../../lib/data-utils";
import { toast } from "sonner";

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
    portfolioInput,
    setPortfolioInput,
    availableStrategies,
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
    let isValid = true;
    Object.entries(params).forEach(([k, v]) => {
      const res = validateParam(k, v.toString());
      if (!res.isValid) {
        toast.error(`Invalid ${k}: ${res.error}`);
        isValid = false;
      }
    });

    const capRes = validateParam("capital", capital);
    if (!capRes.isValid) {
      toast.error(`Capital error: ${capRes.error}`);
      isValid = false;
    }

    const levRes = validateParam("leverage", leverage);
    if (!levRes.isValid) {
      toast.error(`Leverage error: ${levRes.error}`);
      isValid = false;
    }

    const riskRes = validateParam("risk_percent", riskPercent);
    if (!riskRes.isValid) {
      toast.error(`Risk error: ${riskRes.error}`);
      isValid = false;
    }

    if (!isValid) return;

    resetPrep();
    const startTime = Date.now();

    const symbolsToCheck =
      mode === "batch" || mode === "portfolio"
        ? portfolioInput
            .split("\n")
            .map((s) => s.trim())
            .filter((s) => s.length > 0)
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
                Batch
              </button>
              <button
                onClick={() => setMode("portfolio")}
                className={cn(
                  "flex-1 py-2 text-xs font-medium rounded-md transition-all",
                  mode === "portfolio"
                    ? "bg-bg-secondary text-text-primary shadow-sm"
                    : "text-text-secondary hover:text-text-primary"
                )}
              >
                Portfolio
              </button>
            </div>
          </CollapsibleSection>

          {/* Asset Config, Date, Strategy, Params, Risk */}
              {/* Symbol & Timeframe */}
              <CollapsibleSection title="Asset Config">
                <div className="space-y-3">
                  {mode === "single" ? (
                    <div>
                      <label className="text-xs font-medium text-text-secondary mb-1.5 block">
                        Symbol
                      </label>
                      <Select
                        value={symbol}
                        onValueChange={(val) => setSymbol(val)}
                      >
                        <SelectTrigger className="w-full bg-input/50 border-border-main rounded-md px-3 py-3 text-sm text-text-primary focus:ring-1 focus:ring-accent-main/50 h-auto data-[state=open]:bg-bg-elevated shadow-none transition-colors border-none sm:border-solid">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent className="border-border-main bg-bg-surface backdrop-blur-xl shadow-xl">
                          <SelectItem
                            value="BTC/USDT"
                            className="cursor-pointer hover:bg-bg-elevated"
                          >
                            BTC/USDT
                          </SelectItem>
                          <SelectItem
                            value="ETH/USDT"
                            className="cursor-pointer hover:bg-bg-elevated"
                          >
                            ETH/USDT
                          </SelectItem>
                          <SelectItem
                            value="SOL/USDT"
                            className="cursor-pointer hover:bg-bg-elevated"
                          >
                            SOL/USDT
                          </SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                  ) : (
                    <div>
                      <label className="text-xs font-medium text-text-secondary mb-1.5 block">
                        Portfolio Config (Tickers separated by newline)
                      </label>
                      <textarea
                        value={portfolioInput}
                        onChange={(e) => setPortfolioInput(e.target.value)}
                        rows={4}
                        className="w-full bg-input/50 border border-border-main rounded-md px-3 py-2 text-xs text-text-primary focus:outline-none focus:ring-1 focus:ring-accent-main/50 custom-scrollbar resize-y"
                        placeholder="BTC/USDT\nETH/USDT"
                      />
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
                <Select
                  value={strategy}
                  onValueChange={(val) => setStrategy(val)}
                >
                  <SelectTrigger className="w-full bg-input/50 border-border-main rounded-md px-3 py-3 text-sm text-text-primary focus:ring-1 focus:ring-accent-main/50 h-auto data-[state=open]:bg-bg-elevated shadow-none transition-colors border-none sm:border-solid">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent className="border-border-main bg-bg-surface backdrop-blur-xl shadow-xl">
                    {availableStrategies.length > 0 ? (
                      availableStrategies.map((s) => (
                        <SelectItem
                          key={s.name}
                          value={s.name}
                          className="cursor-pointer hover:bg-bg-elevated"
                        >
                          {s.description ||
                            s.name
                              .replace(/_/g, " ")
                              .replace(/\b\w/g, (l) => l.toUpperCase())}
                        </SelectItem>
                      ))
                    ) : (
                      <SelectItem
                        value="rsi_no_retest"
                        className="cursor-pointer hover:bg-bg-elevated"
                      >
                        RSI No Retest
                      </SelectItem>
                    )}
                  </SelectContent>
                </Select>
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
        </div>

        {/* Sticky Footer with Run Button */}
        <div className="absolute bottom-0 left-0 right-0 p-4 border-t border-border-main bg-bg-surface/95 backdrop-blur-md">
            <RunButton onClick={handleRunRequest} />
          </div>
      </SheetContent>
    </Sheet>
  );
};
