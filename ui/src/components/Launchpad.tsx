import React from 'react';
import { useBacktestStore } from '../stores/backtestStore';
import { useSingleRunStore } from '../stores/singleRunStore';
import { useBatchRunStore } from '../stores/batchRunStore';
import { usePortfolioRunStore } from '../stores/portfolioRunStore';
import { Play, Square } from 'lucide-react';

export function Launchpad() {
  const store = useBacktestStore();
  const singleStore = useSingleRunStore();
  const batchStore = useBatchRunStore();
  const portfolioStore = usePortfolioRunStore();

  const handleStart = () => {
    const config = {
      mode: store.mode as 'single' | 'batch' | 'portfolio',
      symbols: store.mode === 'single' ? [store.symbol] : store.portfolioInput.split('\n').filter(s => s.trim() !== ''),
      timeframe: store.timeframe,
      strategy: store.strategy,
      start_date: store.startDate,
      end_date: store.endDate,
      initial_capital: store.capital,
      capital_mode: store.capitalMode,
      leverage: parseInt(store.leverage),
      risk_per_trade_pct: store.riskPercent,
      fee_tier: "0.001",
      slippage_model: "none",
      slippage_pct: "0.0",
      params: store.params
    };

    if (store.mode === 'single') singleStore.run(config);
    if (store.mode === 'batch') batchStore.run(config);
    if (store.mode === 'portfolio') portfolioStore.run(config);
  };

  const handleStop = () => {
    if (store.mode === 'single') singleStore.cancel();
    if (store.mode === 'batch') batchStore.cancel();
    if (store.mode === 'portfolio') portfolioStore.cancel();
  };

  const isRunning = singleStore.isRunning || batchStore.isRunning || portfolioStore.isRunning;
  const progress = store.mode === 'single' ? singleStore.runProgress : store.mode === 'batch' ? batchStore.runProgress : portfolioStore.runProgress;

  return (
    <div className="flex flex-col gap-4 p-4">
       <div className="flex gap-2">
            <button
                onClick={isRunning ? handleStop : handleStart}
                className={`flex-1 flex items-center justify-center gap-2 p-2 rounded ${isRunning ? 'bg-red-600 hover:bg-red-700 text-white' : 'bg-primary hover:bg-primary/90 text-primary-foreground'}`}
            >
                {isRunning ? (<span><Square size={16} /> Stop Backtest</span>) : (<span><Play size={16} /> Start Backtest</span>)}
            </button>
       </div>
       {isRunning && (
            <div className="w-full bg-secondary rounded-full h-2">
                <div className="bg-primary h-2 rounded-full" style={{ width: `${progress}%` }}></div>
            </div>
       )}
       {store.mode === 'batch' && (
           <div className="flex items-center gap-2 mt-4">
               <label className="text-sm font-medium">Capital Mode</label>
               <select
                   value={store.capitalMode}
                   onChange={(e) => store.setCapitalMode(e.target.value as 'split' | 'full')}
               >
                   <option value="split">Split</option>
                   <option value="full">Full</option>
               </select>
           </div>
       )}
       {store.mode !== 'single' && (
           <div className="flex flex-col gap-2 mt-4">
               <label className="text-sm font-medium">Symbols (One per line)</label>
               <textarea
                   className="w-full min-h-[100px] p-2 rounded border bg-background"
                   value={store.portfolioInput}
                   onChange={(e) => store.setPortfolioInput(e.target.value)}
                   placeholder="BTC/USDT\nETH/USDT"
               ></textarea>
           </div>
       )}
    </div>
  );
}
