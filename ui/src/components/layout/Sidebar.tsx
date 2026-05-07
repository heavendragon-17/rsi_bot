// @ts-nocheck
import React, { useEffect, useState } from "react";
import {
  ChevronLeft,
  ChevronRight,
  ChevronUp,
  ChevronDown,
  Settings,
  Play,
  Layers,
  RotateCcw,
  TrendingUp,
  Calendar,
  Activity,
  Sliders,
  History,
} from "lucide-react";
import { useBacktestStore } from "../../stores/backtestStore";
import { useDataPrepStore } from "../../stores/dataPrepStore";
import { checkDataStatus } from "../../lib/data-utils";
import { toast } from "sonner";
import { cn } from "../../lib/utils";
import { CollapsibleSection } from "../ui/CollapsibleSection";
import { ValidatedInput } from "../ui/ValidatedInput";
import { RunButton } from "./RunButton";
import { validateParam } from "../../lib/validation";
import { DateRangeSection } from "../date-controls/DateRangeSection";
import { DynamicParamForm } from "../sidebar/DynamicParamForm";
import { PresetManager } from "../sidebar/PresetManager";
import { Switch } from "../ui/switch";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../ui/select";

export const Sidebar: React.FC = () => {
  const {
    isSidebarOpen,
    toggleSidebar,
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
    tp1ClosePct, setTp1ClosePct,
    tp2ClosePct, setTp2ClosePct,
    maxPositionSizePct, setMaxPositionSizePct,
    minSlDistancePct, setMinSlDistancePct,
    useRiskBasedSizing, setUseRiskBasedSizing,
    useInitialCapitalForRisk, setUseInitialCapitalForRisk,
    enableFees, setEnableFees,
    takerFeePct, setTakerFeePct,
    makerFeePct, setMakerFeePct,
    slippageModel, setSlippageModel,
    slippagePct, setSlippagePct,
    isRunning,
    runBacktest,
    setSidebarOpen,
    startDate,
    endDate,
    portfolioInput,
    setPortfolioInput,
    availableStrategies,
    loadStrategies,
    benchmark,
    setBenchmark,
  } = useBacktestStore();

  const {
    openModal,
    setPrepState,
    setSymbols,
    reset: resetPrep,
  } = useDataPrepStore();

  const executeRun = async () => {
    // backtestStore.runBacktest() handles API call, SSE, results, and history (server-side).
    await runBacktest();
  };

  const handleRunRequest = async () => {
    // 1. Validate inputs
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

    // Data download is now inline (server-side) — go straight to run
    executeRun();
  };

  // Keyboard Shortcuts
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === "[") {
        e.preventDefault();
        toggleSidebar();
      }

      if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
        e.preventDefault();
        handleRunRequest();
      }

      if ((e.ctrlKey || e.metaKey) && e.key === "r") {
        if (e.target instanceof HTMLElement && e.target.tagName !== "INPUT") {
          e.preventDefault();
          resetParams();
        }
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [
    toggleSidebar,
    runBacktest,
    resetParams,
    params,
    capital,
    leverage,
    riskPercent,
    handleRunRequest,
  ]);

  // Load strategies on mount
  useEffect(() => {
    loadStrategies();
  }, [loadStrategies]);

  // Sync relative dates on mount so stale persisted dates (e.g. "2024")
  // are replaced with current dates before the user clicks Run.
  const syncRelativeDates = useBacktestStore((s) => s.syncRelativeDates);
  const dateMode = useBacktestStore((s) => s.dateMode);
  useEffect(() => {
    if (dateMode === "relative") syncRelativeDates();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const sidebarClasses = cn(
    "fixed left-4 top-20 bottom-4 z-40 hidden lg:flex flex-col transition-all duration-300 ease-in-out border border-bg-elevated/50 shadow-xl rounded-xl",
    isSidebarOpen ? "w-[320px] overflow-hidden" : "w-[60px] overflow-visible",
    "bg-bg-surface/60 backdrop-blur-xl",
    isRunning && "pointer-events-none opacity-80 grayscale-[30%]"
  );

  // If in Pine Tool mode, the sidebar might need to look different or be hidden?
  // Let's keep it visible but maybe minimal? Or just let it be.

  return (
    <aside className={sidebarClasses}>
      {/* Header / Collapse Toggle */}
      <div className="flex items-center justify-between p-4 border-b border-border-main/50 h-14 shrink-0 bg-transparent">
        {isSidebarOpen && (
          <span className="font-semibold text-text-primary text-sm tracking-wide">
            CONFIGURATION
          </span>
        )}
        <button
          onClick={toggleSidebar}
          className="p-1.5 rounded-md hover:bg-bg-elevated text-text-secondary transition-colors ml-auto"
        >
          {isSidebarOpen ? (
            <ChevronLeft size={18} />
          ) : (
            <ChevronRight size={18} />
          )}
        </button>
      </div>

      {/* Content Wrapper */}
      <div className="flex-1 relative min-h-0">
        {/* Expanded Scroll Area */}
        <div
          className={cn(
            "absolute inset-0 overflow-y-auto overflow-x-hidden custom-scrollbar pb-4",
            !isSidebarOpen && "hidden"
          )}
        >
          <div className="pb-2">
            {" "}
            {/* Internal Padding */}
            {/* Mode Selection */}
            <CollapsibleSection title="Mode" defaultOpen={true}>
              <div className="grid grid-cols-3 gap-1 bg-bg-elevated p-1 rounded-lg">
                <button
                  onClick={() => setMode("single")}
                  className={cn(
                    "flex-1 py-1.5 text-[10px] font-medium rounded-md transition-all",
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
                    "flex-1 py-1.5 text-[10px] font-medium rounded-md transition-all",
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
                    "flex-1 py-1.5 text-[10px] font-medium rounded-md transition-all",
                    mode === "portfolio"
                      ? "bg-bg-secondary text-text-primary shadow-sm"
                      : "text-text-secondary hover:text-text-primary"
                  )}
                >
                  Portfolio
                </button>
              </div>
            </CollapsibleSection>
            {/* Symbol & Timeframe */}
                {/* Symbol & Timeframe */}
                <CollapsibleSection title="Asset Config">
                  <div className="grid grid-cols-2 gap-3 mb-3">
                    {mode === "single" ? (
                      <div className="col-span-2">
                        <label className="text-xs font-medium text-text-secondary mb-1.5 block">
                          Symbol
                        </label>
                        <input
                          type="text"
                          value={symbol}
                          onChange={(e) => setSymbol(e.target.value.toUpperCase())}
                          placeholder="e.g. BTC/USDT"
                          className="w-full bg-input/50 border border-border-main rounded-md px-3 py-2 text-sm text-text-primary focus:outline-none focus:ring-1 focus:ring-accent-main/50 placeholder:text-text-muted"
                        />
                        <div className="grid grid-cols-3 gap-1.5 mt-2">
                          {["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT", "DOGE/USDT"].map((s) => (
                            <button
                              key={s}
                              onClick={() => setSymbol(s)}
                              className={cn(
                                "px-1.5 py-1.5 text-[10px] font-medium rounded-md border transition-all text-center leading-none",
                                symbol === s
                                  ? "bg-accent-main/15 border-accent-main text-accent-main"
                                  : "bg-bg-elevated border-border-main text-text-secondary hover:border-text-muted hover:text-text-primary"
                              )}
                            >
                              {s.split("/")[0]}
                            </button>
                          ))}
                        </div>
                      </div>
                    ) : (
                      <div className="col-span-2">
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

                    <div className="col-span-2">
                      <label className="text-xs font-medium text-text-secondary mb-1.5 block">
                        Timeframe
                      </label>
                      <div className="grid grid-cols-7 gap-1 mb-1.5">
                        {["1m", "5m", "15m", "30m", "1h", "4h", "1d"].map((tf) => (
                          <button
                            key={tf}
                            onClick={() => setTimeframe(tf)}
                            className={cn(
                              "py-1.5 border rounded-md text-[10px] font-medium transition-colors",
                              timeframe === tf
                                ? "bg-accent-main/10 border-accent-main text-accent-main"
                                : "border-border-main text-text-secondary hover:border-text-muted"
                            )}
                          >
                            {tf}
                          </button>
                        ))}
                      </div>
                      <input
                        type="text"
                        value={timeframe}
                        onChange={(e) => setTimeframe(e.target.value.toLowerCase().trim())}
                        placeholder="Custom (e.g. 3m, 2h, 12h, 1w)"
                        className="w-full bg-input/50 border border-border-main rounded-md px-3 py-1.5 text-xs text-text-primary focus:outline-none focus:ring-1 focus:ring-accent-main/50 placeholder:text-text-muted font-mono"
                      />
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
                    <SelectTrigger className="w-full bg-input/50 border-border-main rounded-md px-3 py-2.5 text-sm text-text-primary focus:ring-1 focus:ring-accent-main/50 h-auto data-[state=open]:bg-bg-elevated shadow-none transition-colors border-none sm:border-solid">
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
                            {/* Assuming name is snake_case identifier or nicely formatted string */}
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

                {/* Dynamic Strategy Parameters */}
                <DynamicParamForm />

                {/* Presets */}
                <PresetManager />

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
                    <div className="grid grid-cols-2 gap-3">
                      <ValidatedInput
                        label="TP1 Close"
                        paramKey="tp1_close_pct"
                        value={tp1ClosePct}
                        onChangeValue={setTp1ClosePct}
                        suffix="%"
                      />
                      <ValidatedInput
                        label="TP2 Close"
                        paramKey="tp2_close_pct"
                        value={tp2ClosePct}
                        onChangeValue={setTp2ClosePct}
                        suffix="%"
                      />
                    </div>
                    <div className="grid grid-cols-2 gap-3">
                      <ValidatedInput
                        label="Max Position"
                        paramKey="max_position_size_pct"
                        value={maxPositionSizePct}
                        onChangeValue={setMaxPositionSizePct}
                        suffix="%"
                      />
                      <ValidatedInput
                        label="Min SL Dist"
                        paramKey="min_sl_distance_pct"
                        value={minSlDistancePct}
                        onChangeValue={setMinSlDistancePct}
                        suffix="%"
                      />
                    </div>
                    <div className="space-y-2">
                      <label className="flex items-center justify-between cursor-pointer">
                        <span className="text-xs text-text-secondary">Risk-Based Sizing</span>
                        <Switch checked={useRiskBasedSizing} onCheckedChange={setUseRiskBasedSizing} />
                      </label>
                      <label className="flex items-center justify-between cursor-pointer">
                        <span className="text-xs text-text-secondary">Risk Off Initial Capital</span>
                        <Switch checked={useInitialCapitalForRisk} onCheckedChange={setUseInitialCapitalForRisk} />
                      </label>
                    </div>
                  </div>
                </CollapsibleSection>

                {/* Benchmark */}
                <CollapsibleSection title="Benchmark">
                  <div className="space-y-2">
                    <label className="text-xs font-medium text-text-secondary block">
                      Buy-and-hold comparison
                    </label>
                    <Select
                      value={benchmark ?? "none"}
                      onValueChange={(val) => setBenchmark(val === "none" ? null : val)}
                    >
                      <SelectTrigger className="w-full bg-input/50 border-border-main rounded-md px-3 py-2.5 text-sm text-text-primary focus:ring-1 focus:ring-accent-main/50 h-auto shadow-none transition-colors">
                        <SelectValue placeholder="None (disabled)" />
                      </SelectTrigger>
                      <SelectContent className="border-border-main bg-bg-surface backdrop-blur-xl shadow-xl">
                        <SelectItem value="none">None (disabled)</SelectItem>
                        {["BTC/USDT", "ETH/USDT", "SOL/USDT", "HYPE/USDT", "BNB/USDT", "XRP/USDT"].map((s) => (
                          <SelectItem key={s} value={s}>{s}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                </CollapsibleSection>

                {/* Fees & Slippage */}
                <CollapsibleSection title="Fees & Slippage">
                  <div className="space-y-3">
                    <label className="flex items-center justify-between cursor-pointer">
                      <span className="text-xs text-text-secondary">Enable Fees</span>
                      <Switch checked={enableFees} onCheckedChange={setEnableFees} />
                    </label>
                    {enableFees && (
                      <div className="space-y-2">
                        <style>{`
                          .fee-input::-webkit-outer-spin-button,
                          .fee-input::-webkit-inner-spin-button { -webkit-appearance: none; margin: 0; }
                          .fee-input { -moz-appearance: textfield; }
                        `}</style>
                        {[
                          { label: "Taker Fee", value: takerFeePct, onChange: setTakerFeePct, presets: ["0.05", "0.06", "0.10", "0.20"] },
                          { label: "Maker Fee", value: makerFeePct, onChange: setMakerFeePct, presets: ["0.02", "0.04", "0.06", "0.10"] },
                        ].map(({ label, value, onChange, presets }) => (
                          <div key={label}>
                            <label className="text-xs font-medium text-text-secondary mb-1.5 block">{label}</label>
                            <div className="flex gap-1 mb-1.5">
                              {presets.map((p) => (
                                <button
                                  key={p}
                                  onClick={() => onChange(p)}
                                  className={cn(
                                    "flex-1 py-1 text-[10px] font-medium rounded-md border transition-all",
                                    value === p
                                      ? "bg-accent-main/10 border-accent-main text-accent-main"
                                      : "border-border-main text-text-secondary hover:border-text-muted"
                                  )}
                                >
                                  {p}%
                                </button>
                              ))}
                            </div>
                            <div className="flex items-center h-9 bg-input/50 border border-border-main rounded-md px-3 focus-within:ring-1 focus-within:ring-accent-main/50 transition-colors">
                              <input
                                type="number"
                                min="0"
                                step="0.01"
                                value={value}
                                onChange={(e) => onChange(e.target.value)}
                                className="flex-1 min-w-0 bg-transparent border-none text-sm text-text-primary focus:outline-none p-0 fee-input"
                              />
                              <span className="text-xs text-text-muted mr-2">%</span>
                              <div className="flex flex-col items-center justify-center shrink-0 border-l border-border-main/50 pl-1.5 ml-1">
                                <button
                                  onClick={() => onChange((Math.round((parseFloat(value || "0") + 0.01) * 100) / 100).toFixed(2))}
                                  className="text-text-muted hover:text-text-primary transition-colors focus:outline-none h-[12px] flex items-end justify-center"
                                  tabIndex={-1}
                                >
                                  <ChevronUp size={12} strokeWidth={3} />
                                </button>
                                <button
                                  onClick={() => onChange((Math.round((Math.max(0, parseFloat(value || "0") - 0.01)) * 100) / 100).toFixed(2))}
                                  className="text-text-muted hover:text-text-primary transition-colors focus:outline-none h-[12px] flex items-start justify-center mt-0.5"
                                  tabIndex={-1}
                                >
                                  <ChevronDown size={12} strokeWidth={3} />
                                </button>
                              </div>
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                    <div>
                      <label className="text-xs font-medium text-text-secondary mb-1.5 block">
                        Slippage Model
                      </label>
                      <div className="flex gap-1.5">
                        {(["none", "fixed"] as const).map((m) => (
                          <button
                            key={m}
                            onClick={() => setSlippageModel(m)}
                            className={cn(
                              "flex-1 py-1.5 text-[10px] font-medium rounded-md border transition-all capitalize",
                              slippageModel === m
                                ? "bg-accent-main/10 border-accent-main text-accent-main"
                                : "border-border-main text-text-secondary hover:border-text-muted"
                            )}
                          >
                            {m}
                          </button>
                        ))}
                      </div>
                    </div>
                    {slippageModel === "fixed" && (
                      <ValidatedInput
                        label="Slippage %"
                        paramKey="slippage_pct"
                        value={slippagePct}
                        onChangeValue={setSlippagePct}
                        suffix="%"
                      />
                    )}
                  </div>
                </CollapsibleSection>

          </div>
        </div>

        {/* Collapsed View (No Scroll) */}
        {!isSidebarOpen && (
          <div className="flex flex-col items-center gap-6 py-6 w-full">
            <div className="group relative flex justify-center w-full">
              <Layers
                size={20}
                className="text-text-secondary group-hover:text-text-primary transition-colors"
              />
            </div>

            <div className="group relative flex justify-center w-full">
              <TrendingUp
                size={20}
                className="text-text-secondary group-hover:text-text-primary transition-colors"
              />
            </div>

            <div className="group relative flex justify-center w-full">
              <Calendar
                size={20}
                className="text-text-secondary group-hover:text-text-primary transition-colors"
              />
            </div>

          </div>
        )}

        {/* Scroll Fade Mask (Expanded Only) */}
        {isSidebarOpen && (
          <div className="absolute bottom-0 left-0 right-0 h-10 bg-gradient-to-t from-bg-surface to-transparent pointer-events-none z-10" />
        )}
      </div>

        <div className="p-4 border-t border-border-main/50 bg-bg-surface/80 backdrop-blur-md shrink-0 z-20">
          {isSidebarOpen ? (
            <RunButton onClick={handleRunRequest} />
          ) : (
            <button
              onClick={() => setSidebarOpen(true)}
              className="w-full h-10 rounded-lg bg-accent-main hover:bg-accent-hover flex items-center justify-center text-white shadow-lg transition-colors"
            >
              <Play size={18} className="fill-current" />
            </button>
          )}
        </div>
    </aside>
  );
};
