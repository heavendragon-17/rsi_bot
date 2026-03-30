// @ts-nocheck
import React, { useEffect, useState } from "react";
import {
  ChevronLeft,
  ChevronRight,
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
    isRunning,
    runBacktest,
    setSidebarOpen,
    startDate,
    endDate,
    portfolioInput,
    setPortfolioInput,
    availableStrategies,
    loadStrategies,
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
                        <Select
                          value={symbol}
                          onValueChange={(val) => setSymbol(val)}
                        >
                          <SelectTrigger className="w-full bg-input/50 border-border-main rounded-md px-3 py-2.5 text-sm text-text-primary focus:ring-1 focus:ring-accent-main/50 h-auto data-[state=open]:bg-bg-elevated shadow-none transition-colors border-none sm:border-solid">
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
                      <div className="flex gap-2">
                        {["15m", "1h", "4h", "1d"].map((tf) => (
                          <button
                            key={tf}
                            onClick={() => setTimeframe(tf)}
                            className={cn(
                              "flex-1 py-1.5 border rounded-md text-xs font-medium transition-colors",
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
