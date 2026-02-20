// @ts-nocheck
import { useState } from 'react';
import { LaunchpadConfig, StrategyConfig, TakeProfit } from '../App';
import { ChevronRight, Sliders, Target, Shield, Save, Rocket, ArrowLeft, Plus, Trash2, Activity } from 'lucide-react';
import { motion } from 'motion/react';
import { Input } from './ui/input';
import { Label } from './ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from './ui/select';

interface StrategyLabProps {
  onRunBacktest: (config: StrategyConfig) => void;
  config: StrategyConfig;
  launchpadConfig: LaunchpadConfig;
  onBack: () => void;
}

export function StrategyLab({ onRunBacktest, config, launchpadConfig, onBack }: StrategyLabProps) {
  const [strategyName, setStrategyName] = useState(config.strategyName);
  
  // Oscillators
  const [rsiPeriod, setRsiPeriod] = useState(config.rsiPeriod.toString());
  const [rsiEmaLength, setRsiEmaLength] = useState(config.rsiEmaLength.toString());
  const [rsiWmaLength, setRsiWmaLength] = useState(config.rsiWmaLength.toString());
  const [priceEmaFast, setPriceEmaFast] = useState(config.priceEmaFast.toString());
  const [priceEmaSlow, setPriceEmaSlow] = useState(config.priceEmaSlow.toString());
  
  // Entry Conditions
  const [lookback, setLookback] = useState(config.lookback.toString());
  const [maxAboveEma21, setMaxAboveEma21] = useState(config.maxAboveEma21.toString());
  const [minRsiSpread, setMinRsiSpread] = useState(config.minRsiSpread.toString());
  
  // Risk & Exit
  const [slMode, setSlMode] = useState(config.slMode);
  const [slBuffer, setSlBuffer] = useState(config.slBuffer.toString());
  const [disasterSlMultiplier, setDisasterSlMultiplier] = useState(config.disasterSlMultiplier.toString());
  const [takeProfits, setTakeProfits] = useState<TakeProfit[]>(config.takeProfits);
  const [candleCloseSlippage, setCandleCloseSlippage] = useState(config.candleCloseSlippage.toString());
  const [moveSlTrigger, setMoveSlTrigger] = useState(config.moveSlTrigger.toString());
  const [lockProfitLevel, setLockProfitLevel] = useState(config.lockProfitLevel.toString());

  const slModes = ['lowest_close', 'rsi_ema9', 'lowest_wick'];
  const strategies = ['rsi_no_retest', 'ema_crossover', 'momentum_scalper'];

  const handleAddTakeProfit = () => {
    setTakeProfits([...takeProfits, { rMultiple: 1.0, closePercent: 0 }]);
  };

  const handleRemoveTakeProfit = (index: number) => {
    setTakeProfits(takeProfits.filter((_, i) => i !== index));
  };

  const handleTakeProfitChange = (index: number, field: 'rMultiple' | 'closePercent', value: string) => {
    const updated = [...takeProfits];
    updated[index] = {
      ...updated[index],
      [field]: parseFloat(value) || 0
    };
    setTakeProfits(updated);
  };

  const handleRunBacktest = () => {
    onRunBacktest({
      strategyName,
      rsiPeriod: parseFloat(rsiPeriod),
      rsiEmaLength: parseFloat(rsiEmaLength),
      rsiWmaLength: parseFloat(rsiWmaLength),
      priceEmaFast: parseFloat(priceEmaFast),
      priceEmaSlow: parseFloat(priceEmaSlow),
      lookback: parseFloat(lookback),
      maxAboveEma21: parseFloat(maxAboveEma21),
      minRsiSpread: parseFloat(minRsiSpread),
      slMode,
      slBuffer: parseFloat(slBuffer),
      disasterSlMultiplier: parseFloat(disasterSlMultiplier),
      takeProfits,
      candleCloseSlippage: parseFloat(candleCloseSlippage),
      moveSlTrigger: parseFloat(moveSlTrigger),
      lockProfitLevel: parseFloat(lockProfitLevel),
    });
  };

  return (
    <div className="min-h-screen p-8">
      <div className="max-w-7xl mx-auto space-y-8">
        {/* Header with Breadcrumb */}
        <motion.div
          initial={{ opacity: 0, y: -20 }}
          animate={{ opacity: 1, y: 0 }}
          className="space-y-4"
        >
          <div className="flex items-center gap-2 text-sm text-slate-400">
            <button
              onClick={onBack}
              className="flex items-center gap-2 hover:text-violet-400 transition-colors"
            >
              <ArrowLeft className="w-4 h-4" />
              Launchpad
            </button>
            <ChevronRight className="w-4 h-4" />
            <span className="text-violet-400 font-medium">Strategy Lab</span>
          </div>
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-4xl font-bold bg-gradient-to-r from-violet-400 to-cyan-400 bg-clip-text text-transparent">
                Strategy Lab
              </h1>
              <p className="text-slate-400 mt-2">Fine-tune your trading logic parameters</p>
            </div>
            <div className="bg-slate-800/40 backdrop-blur-xl rounded-xl px-6 py-3 border border-white/10">
              <div className="text-xs text-slate-400">Testing Mode</div>
              <div className="text-white font-medium">
                {launchpadConfig.mode === 'single' 
                  ? `${launchpadConfig.symbol} · ${launchpadConfig.timeframe}`
                  : `Batch · ${launchpadConfig.timeframe}`}
              </div>
            </div>
          </div>
        </motion.div>

        {/* Strategy Selector */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.1 }}
          className="bg-slate-800/40 backdrop-blur-xl rounded-2xl p-6 border border-violet-500/30 shadow-[0_0_40px_rgba(139,92,246,0.2)]"
        >
          <div className="flex items-center gap-4">
            <div className="p-3 bg-violet-500/20 rounded-lg">
              <Target className="w-6 h-6 text-violet-400" />
            </div>
            <div className="flex-1">
              <Label className="text-slate-300 text-xs">Strategy Template</Label>
              <Select value={strategyName} onValueChange={setStrategyName}>
                <SelectTrigger className="w-full mt-1 bg-slate-900/50 border-white/10 text-white">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {strategies.map((strat) => (
                    <SelectItem key={strat} value={strat}>
                      {strat}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
        </motion.div>

        {/* Configuration Grid */}
        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6">
          {/* Oscillators Panel */}
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.15 }}
            className="bg-slate-800/40 backdrop-blur-xl rounded-2xl p-6 border border-white/10 space-y-6"
          >
            <div className="flex items-center gap-3 pb-4 border-b border-white/10">
              <Sliders className="w-5 h-5 text-cyan-400" />
              <h3 className="font-bold text-white">Oscillators (Indicators)</h3>
            </div>
            
            <div className="space-y-4">
              <div className="space-y-2">
                <Label className="text-slate-300 text-sm">RSI Period</Label>
                <Input
                  type="number"
                  value={rsiPeriod}
                  onChange={(e) => setRsiPeriod(e.target.value)}
                  className="bg-slate-900/50 border-white/10 text-white font-mono"
                />
                <div className="text-xs text-slate-500">Default: 21</div>
              </div>

              <div className="space-y-2">
                <Label className="text-slate-300 text-sm">RSI EMA Length</Label>
                <Input
                  type="number"
                  value={rsiEmaLength}
                  onChange={(e) => setRsiEmaLength(e.target.value)}
                  className="bg-slate-900/50 border-white/10 text-white font-mono"
                />
                <div className="text-xs text-slate-500">Default: 9</div>
              </div>

              <div className="space-y-2">
                <Label className="text-slate-300 text-sm">RSI WMA Length</Label>
                <Input
                  type="number"
                  value={rsiWmaLength}
                  onChange={(e) => setRsiWmaLength(e.target.value)}
                  className="bg-slate-900/50 border-white/10 text-white font-mono"
                />
                <div className="text-xs text-slate-500">Default: 45</div>
              </div>

              <div className="space-y-2">
                <Label className="text-slate-300 text-sm">Price EMA Fast</Label>
                <Input
                  type="number"
                  value={priceEmaFast}
                  onChange={(e) => setPriceEmaFast(e.target.value)}
                  className="bg-slate-900/50 border-white/10 text-white font-mono"
                />
                <div className="text-xs text-slate-500">Default: 21</div>
              </div>

              <div className="space-y-2">
                <Label className="text-slate-300 text-sm">Price EMA Slow</Label>
                <Input
                  type="number"
                  value={priceEmaSlow}
                  onChange={(e) => setPriceEmaSlow(e.target.value)}
                  className="bg-slate-900/50 border-white/10 text-white font-mono"
                />
                <div className="text-xs text-slate-500">Default: 200</div>
              </div>
            </div>
          </motion.div>

          {/* Entry Conditions Panel */}
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.2 }}
            className="bg-slate-800/40 backdrop-blur-xl rounded-2xl p-6 border border-white/10 space-y-6"
          >
            <div className="flex items-center gap-3 pb-4 border-b border-white/10">
              <Activity className="w-5 h-5 text-violet-400" />
              <h3 className="font-bold text-white">Entry Conditions</h3>
            </div>
            
            <div className="space-y-4">
              <div className="space-y-2">
                <Label className="text-slate-300 text-sm">Lookback Period</Label>
                <Input
                  type="number"
                  value={lookback}
                  onChange={(e) => setLookback(e.target.value)}
                  className="bg-slate-900/50 border-white/10 text-white font-mono"
                />
                <div className="text-xs text-slate-500">nr_lookback (Default: 30)</div>
              </div>

              <div className="space-y-2">
                <Label className="text-slate-300 text-sm">Max Above EMA21</Label>
                <Input
                  type="number"
                  value={maxAboveEma21}
                  onChange={(e) => setMaxAboveEma21(e.target.value)}
                  className="bg-slate-900/50 border-white/10 text-white font-mono"
                />
                <div className="text-xs text-slate-500">nr_max_above_ema21 (Default: 1)</div>
              </div>

              <div className="space-y-2">
                <Label className="text-slate-300 text-sm">Min RSI Spread</Label>
                <Input
                  type="number"
                  step="0.1"
                  value={minRsiSpread}
                  onChange={(e) => setMinRsiSpread(e.target.value)}
                  className="bg-slate-900/50 border-white/10 text-white font-mono"
                />
                <div className="text-xs text-slate-500">nr_rsi_spread_min (Default: 1.5)</div>
              </div>
            </div>
          </motion.div>

          {/* Stop Loss Configuration */}
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.25 }}
            className="bg-slate-800/40 backdrop-blur-xl rounded-2xl p-6 border border-white/10 space-y-6"
          >
            <div className="flex items-center gap-3 pb-4 border-b border-white/10">
              <Shield className="w-5 h-5 text-rose-400" />
              <h3 className="font-bold text-white">Stop Loss Config</h3>
            </div>
            
            <div className="space-y-4">
              <div className="space-y-2">
                <Label className="text-slate-300 text-sm">SL Mode</Label>
                <Select value={slMode} onValueChange={setSlMode}>
                  <SelectTrigger className="bg-slate-900/50 border-white/10 text-white">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {slModes.map((mode) => (
                      <SelectItem key={mode} value={mode}>
                        {mode}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-2">
                <Label className="text-slate-300 text-sm">SL Buffer (%)</Label>
                <Input
                  type="number"
                  step="0.1"
                  value={slBuffer}
                  onChange={(e) => setSlBuffer(e.target.value)}
                  className="bg-slate-900/50 border-white/10 text-white font-mono"
                />
                <div className="text-xs text-slate-500">Default: 0.0%</div>
              </div>

              <div className="space-y-2">
                <Label className="text-slate-300 text-sm">Disaster SL Multiplier</Label>
                <Input
                  type="number"
                  step="0.1"
                  value={disasterSlMultiplier}
                  onChange={(e) => setDisasterSlMultiplier(e.target.value)}
                  className="bg-slate-900/50 border-white/10 text-white font-mono"
                />
                <div className="text-xs text-slate-500">Default: 3.0</div>
              </div>
            </div>
          </motion.div>
        </div>

        {/* Take Profits & SL Management - Full Width */}
        <div className="grid lg:grid-cols-2 gap-6">
          {/* Take Profits */}
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.3 }}
            className="bg-slate-800/40 backdrop-blur-xl rounded-2xl p-6 border border-white/10 space-y-4"
          >
            <div className="flex items-center justify-between pb-4 border-b border-white/10">
              <h3 className="font-bold text-white flex items-center gap-2">
                <Target className="w-5 h-5 text-emerald-400" />
                Take Profit Targets
              </h3>
              <button
                onClick={handleAddTakeProfit}
                className="p-2 bg-emerald-500/20 hover:bg-emerald-500/30 text-emerald-400 rounded-lg transition-colors"
              >
                <Plus className="w-4 h-4" />
              </button>
            </div>

            <div className="space-y-3">
              {takeProfits.map((tp, index) => (
                <div key={index} className="flex gap-3 items-center">
                  <div className="flex-1 grid grid-cols-2 gap-2">
                    <div>
                      <Label className="text-xs text-slate-400">R Multiple</Label>
                      <Input
                        type="number"
                        step="0.1"
                        value={tp.rMultiple}
                        onChange={(e) => handleTakeProfitChange(index, 'rMultiple', e.target.value)}
                        className="bg-slate-900/50 border-white/10 text-white font-mono text-sm"
                        placeholder="1.0"
                      />
                    </div>
                    <div>
                      <Label className="text-xs text-slate-400">Close %</Label>
                      <Input
                        type="number"
                        value={tp.closePercent}
                        onChange={(e) => handleTakeProfitChange(index, 'closePercent', e.target.value)}
                        className="bg-slate-900/50 border-white/10 text-white font-mono text-sm"
                        placeholder="50"
                      />
                    </div>
                  </div>
                  <button
                    onClick={() => handleRemoveTakeProfit(index)}
                    className="p-2 bg-rose-500/20 hover:bg-rose-500/30 text-rose-400 rounded-lg transition-colors mt-5"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              ))}
            </div>

            <div className="pt-4 border-t border-white/10">
              <div className="space-y-2">
                <Label className="text-slate-300 text-sm">Candle Close Slippage (%)</Label>
                <Input
                  type="number"
                  step="0.1"
                  value={candleCloseSlippage}
                  onChange={(e) => setCandleCloseSlippage(e.target.value)}
                  className="bg-slate-900/50 border-white/10 text-white font-mono"
                />
                <div className="text-xs text-slate-500">Default: 0%</div>
              </div>
            </div>
          </motion.div>

          {/* SL Management */}
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.35 }}
            className="bg-slate-800/40 backdrop-blur-xl rounded-2xl p-6 border border-white/10 space-y-6"
          >
            <div className="flex items-center gap-3 pb-4 border-b border-white/10">
              <Shield className="w-5 h-5 text-cyan-400" />
              <h3 className="font-bold text-white">SL Management</h3>
            </div>

            <div className="space-y-4">
              <div className="space-y-2">
                <Label className="text-slate-300 text-sm">Move SL Trigger (R)</Label>
                <Input
                  type="number"
                  step="0.1"
                  value={moveSlTrigger}
                  onChange={(e) => setMoveSlTrigger(e.target.value)}
                  className="bg-slate-900/50 border-white/10 text-white font-mono"
                />
                <div className="text-xs text-slate-500">When to move SL to breakeven (Default: 0.5R)</div>
              </div>

              <div className="space-y-2">
                <Label className="text-slate-300 text-sm">Lock Profit Level (R)</Label>
                <Input
                  type="number"
                  step="0.1"
                  value={lockProfitLevel}
                  onChange={(e) => setLockProfitLevel(e.target.value)}
                  className="bg-slate-900/50 border-white/10 text-white font-mono"
                />
                <div className="text-xs text-slate-500">Lock in profit at this level (Default: 0.2R)</div>
              </div>
            </div>

            <div className="bg-slate-900/50 rounded-lg p-4 border border-cyan-500/20">
              <div className="text-xs text-slate-400 mb-2">Risk Management Summary</div>
              <div className="space-y-1 text-sm text-slate-300 font-mono">
                <div>• Move SL at {moveSlTrigger}R</div>
                <div>• Lock profit at {lockProfitLevel}R</div>
                <div>• {takeProfits.length} TP levels configured</div>
              </div>
            </div>
          </motion.div>
        </div>

        {/* Action Bar */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.4 }}
          className="flex gap-4"
        >
          <button className="px-6 py-4 bg-slate-800/40 backdrop-blur-xl border border-white/10 hover:border-violet-500/30 text-white rounded-xl transition-all duration-300 flex items-center gap-2">
            <Save className="w-5 h-5" />
            Save Config Template
          </button>
          
          <button
            onClick={handleRunBacktest}
            className="flex-1 py-4 rounded-xl font-bold text-lg bg-gradient-to-r from-violet-600 via-purple-600 to-cyan-600 hover:from-violet-500 hover:via-purple-500 hover:to-cyan-500 text-white shadow-[0_0_40px_rgba(139,92,246,0.4)] hover:shadow-[0_0_60px_rgba(139,92,246,0.6)] transition-all duration-300 flex items-center justify-center gap-3 relative overflow-hidden group active:scale-95"
          >
            <div className="absolute inset-0 bg-gradient-to-r from-white/0 via-white/20 to-white/0 -translate-x-full group-hover:translate-x-full transition-transform duration-1000" />
            <Rocket className="w-6 h-6" />
            RUN BACKTEST
          </button>
        </motion.div>
      </div>
    </div>
  );
}
