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
    Code,
    History
} from "lucide-react";
import { useBacktestStore } from "../../stores/backtestStore";
import { useDataPrepStore } from "../../stores/dataPrepStore";
import { checkDataStatus } from "../../lib/data-utils";
import { cn } from "../../lib/utils";
import { CollapsibleSection } from "../ui/CollapsibleSection";
import { ValidatedInput } from "../ui/ValidatedInput";
import { RunButton } from "./RunButton";
import { validateParam } from "../../lib/validation";
import { DateRangeSection } from "../date-controls/DateRangeSection";
import { ThemeSettings } from "../theme/ThemeSettings";

export const Sidebar: React.FC = () => {
  const [settingsOpen, setSettingsOpen] = useState(false);

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
    endDate
  } = useBacktestStore();

  const { 
      openModal, 
      setPrepState, 
      setSymbols, 
      reset: resetPrep 
  } = useDataPrepStore();

  const executeRun = async () => {
      // backtestStore.runBacktest() handles API call, SSE, results, and history (server-side).
      await runBacktest();
  };

  const handleRunRequest = async () => {
      if (mode === "pine") {
          // If in Pine Tool, maybe "Run" means "Test this script"? 
          // For now, let's just force switch to Single mode with defaults or warn.
          // Or just do nothing.
          return;
      }

      // 1. Validate inputs
      let isValid = true;
      Object.entries(params).forEach(([k, v]) => {
          if (!validateParam(k, v.toString()).isValid) isValid = false;
      });
      if (!validateParam("capital", capital).isValid) isValid = false;
      if (!validateParam("leverage", leverage).isValid) isValid = false;
      if (!validateParam("risk_percent", riskPercent).isValid) isValid = false;
      
      if (!isValid) return; 

      // 2. Data Check Logic (Grace Period)
      resetPrep(); 
      const startTime = Date.now();
      
      const symbolsToCheck = mode === "batch" 
          ? ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "ADA/USDT", "XRP/USDT", "DOGE/USDT", "DOT/USDT", "MATIC/USDT", "LTC/USDT", "UNI/USDT", "LINK/USDT"] 
          : [symbol];

      try {
          const { allFresh, symbolStatuses } = await checkDataStatus(symbolsToCheck, timeframe, startDate, endDate);
          
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
          if (e.target instanceof HTMLElement && e.target.tagName !== 'INPUT') {
            e.preventDefault();
            resetParams();
          }
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [toggleSidebar, runBacktest, resetParams, params, capital, leverage, riskPercent, handleRunRequest]); 

  const sidebarClasses = cn(
    "fixed left-4 top-20 bottom-4 z-40 hidden lg:flex flex-col transition-all duration-300 ease-in-out border border-bg-elevated/50 shadow-xl rounded-xl",
    isSidebarOpen ? "w-[320px] overflow-hidden" : "w-[60px] overflow-visible",
    "bg-bg-surface/60 backdrop-blur-xl",
    isRunning && "locked grayscale-[80%] cursor-not-allowed"
  );

  // If in Pine Tool mode, the sidebar might need to look different or be hidden?
  // Let's keep it visible but maybe minimal? Or just let it be.

  return (
    <aside className={sidebarClasses}>
        {/* Header / Collapse Toggle */}
        <div className="flex items-center justify-between p-4 border-b border-border-main/50 h-14 shrink-0 bg-transparent">
            {isSidebarOpen && (
                <span className="font-semibold text-text-primary text-sm tracking-wide">CONFIGURATION</span>
            )}
            <button 
                onClick={toggleSidebar}
                className="p-1.5 rounded-md hover:bg-bg-elevated text-text-secondary transition-colors ml-auto"
            >
                {isSidebarOpen ? <ChevronLeft size={18} /> : <ChevronRight size={18} />}
            </button>
        </div>

        {/* Content Wrapper */}
        <div className="flex-1 relative min-h-0">
             {/* Expanded Scroll Area */}
             <div className={cn(
                "absolute inset-0 overflow-y-auto overflow-x-hidden custom-scrollbar pb-4",
                !isSidebarOpen && "hidden"
             )}>
                <div className="pb-2"> {/* Internal Padding */}
                    
                    {/* Mode Selection */}
                    <CollapsibleSection title="Mode" defaultOpen={true}>
                        <div className="grid grid-cols-3 gap-1 bg-bg-elevated p-1 rounded-lg">
                            <button 
                                onClick={() => setMode("single")}
                                className={cn(
                                    "flex-1 py-1.5 text-[10px] font-medium rounded-md transition-all",
                                    mode === "single" ? "bg-bg-secondary text-text-primary shadow-sm" : "text-text-secondary hover:text-text-primary"
                                )}
                            >
                                Single
                            </button>
                            <button 
                                onClick={() => setMode("batch")}
                                className={cn(
                                    "flex-1 py-1.5 text-[10px] font-medium rounded-md transition-all",
                                    mode === "batch" ? "bg-bg-secondary text-text-primary shadow-sm" : "text-text-secondary hover:text-text-primary"
                                )}
                            >
                                Portfolio
                            </button>
                             <button 
                                onClick={() => setMode("pine")}
                                className={cn(
                                    "flex-1 py-1.5 text-[10px] font-medium rounded-md transition-all flex items-center justify-center gap-1",
                                    mode === "pine" ? "bg-bg-secondary text-accent-main shadow-sm" : "text-text-secondary hover:text-text-primary"
                                )}
                            >
                                <Code size={10} />
                                Pine
                            </button>
                        </div>
                    </CollapsibleSection>

                    {/* Only show Strategy/Asset config if NOT in Pine mode */}
                    {mode !== "pine" && (
                    <>
                        {/* Symbol & Timeframe */}
                        <CollapsibleSection title="Asset Config">
                            <div className="grid grid-cols-2 gap-3 mb-3">
                                {mode === "single" ? (
                                    <div className="col-span-2">
                                        <label className="text-xs font-medium text-text-secondary mb-1.5 block">Symbol</label>
                                        <div className="relative">
                                            <select 
                                                value={symbol}
                                                onChange={(e) => setSymbol(e.target.value)}
                                                className="w-full appearance-none bg-input/50 border border-border-main rounded-md px-3 py-2 text-sm text-text-primary focus:outline-none focus:ring-1 focus:ring-accent-main/50"
                                            >
                                                <option value="BTC/USDT">BTC/USDT</option>
                                                <option value="ETH/USDT">ETH/USDT</option>
                                                <option value="SOL/USDT">SOL/USDT</option>
                                            </select>
                                            <ChevronRight className="absolute right-3 top-1/2 -translate-y-1/2 rotate-90 text-text-muted pointer-events-none" size={14} />
                                        </div>
                                    </div>
                                ) : (
                                    <div className="col-span-2">
                                        <label className="text-xs font-medium text-text-secondary mb-1.5 block">Portfolio Config</label>
                                        <div className="p-3 bg-bg-elevated rounded border border-border-main text-xs text-text-secondary">
                                            <div className="flex items-center gap-2 mb-1">
                                                <Layers size={14} className="text-accent-main" />
                                                <span className="font-semibold text-text-primary">12 Assets Selected</span>
                                            </div>
                                            <div className="opacity-75">BTC, ETH, SOL, BNB, ADA...</div>
                                        </div>
                                    </div>
                                )}
                                
                                <div className="col-span-2">
                                    <label className="text-xs font-medium text-text-secondary mb-1.5 block">Timeframe</label>
                                    <div className="flex gap-2">
                                        {['15m', '1h', '4h', '1d'].map(tf => (
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
                             <div className="relative">
                                <select 
                                    value={strategy}
                                    onChange={(e) => setStrategy(e.target.value)}
                                    className="w-full appearance-none bg-input/50 border border-border-main rounded-md px-3 py-2 text-sm text-text-primary focus:outline-none focus:ring-1 focus:ring-accent-main/50"
                                >
                                    <option value="rsi_no_retest">RSI No Retest</option>
                                    <option value="macd_cross">MACD Crossover</option>
                                    <option value="bollinger_breakout">Bollinger Breakout</option>
                                    {/* Ideally we would populate this with Saved Pine Indicators too */}
                                </select>
                                <Settings className="absolute right-3 top-1/2 -translate-y-1/2 text-text-muted pointer-events-none" size={14} />
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

                    {/* Pine Tool Instructions (only if Pine mode) */}
                    {mode === "pine" && (
                         <div className="p-4 text-xs text-text-muted italic">
                             Use the Pine Script Translator to import strategies from TradingView. 
                             <br/><br/>
                             Once saved, they will appear in your Strategy list.
                         </div>
                    )}

                    {/* Settings Section */}
                    <CollapsibleSection 
                        title="Settings" 
                        defaultOpen={settingsOpen}
                        onToggle={(isOpen) => setSettingsOpen(isOpen)}
                    >
                        <ThemeSettings />
                    </CollapsibleSection>
                </div>
            </div>

            {/* Collapsed View (No Scroll) */}
            {!isSidebarOpen && (
                 <div className="flex flex-col items-center gap-6 py-6 w-full">
                    <div className="group relative flex justify-center w-full">
                         <Layers size={20} className="text-text-secondary group-hover:text-text-primary transition-colors" />
                    </div>
                    
                    <div className="group relative flex justify-center w-full">
                         <TrendingUp size={20} className="text-text-secondary group-hover:text-text-primary transition-colors" />
                    </div>

                    <div className="group relative flex justify-center w-full">
                         <Calendar size={20} className="text-text-secondary group-hover:text-text-primary transition-colors" />
                    </div>

                    <div className="group relative flex justify-center w-full">
                         <Code size={20} className="text-text-secondary group-hover:text-text-primary transition-colors cursor-pointer" />
                    </div>

                    <button 
                        onClick={() => {
                            setSidebarOpen(true);
                            setSettingsOpen(true);
                        }}
                        className="group relative flex justify-center w-full"
                    >
                         <Settings size={20} className="text-text-secondary group-hover:text-text-primary transition-colors cursor-pointer" />
                    </button>
                </div>
            )}
            
            {/* Scroll Fade Mask (Expanded Only) */}
            {isSidebarOpen && (
                <div className="absolute bottom-0 left-0 right-0 h-10 bg-gradient-to-t from-bg-surface to-transparent pointer-events-none z-10" />
            )}
        </div>

        {/* Sticky Footer (RUN Button) - Hide in Pine mode? Or change text? */}
        {mode !== "pine" && (
            <div className="p-4 border-t border-border-main/50 bg-bg-surface/80 backdrop-blur-md shrink-0 z-20">
                {isSidebarOpen ? (
                    <RunButton 
                        onClick={handleRunRequest}
                    />
                ) : (
                    <button 
                        onClick={() => setSidebarOpen(true)}
                        className="w-full h-10 rounded-lg bg-accent-main hover:bg-accent-hover flex items-center justify-center text-white shadow-lg transition-colors"
                    >
                        <Play size={18} className="fill-current" />
                    </button>
                )}
            </div>
        )}
    </aside>
  );
};