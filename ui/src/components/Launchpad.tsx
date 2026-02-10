import { useState } from 'react';
import { BacktestMode, LaunchpadConfig } from '../App';
import { Target, LayersIcon, ChevronRight, Server, DollarSign, TrendingUp, Shield, Users } from 'lucide-react';
import { motion } from 'motion/react';
import { Input } from './ui/input';
import { Label } from './ui/label';
import { Switch } from './ui/switch';
import { Slider } from './ui/slider';

interface LaunchpadProps {
  onNext: (config: LaunchpadConfig) => void;
  config: LaunchpadConfig;
}

export function Launchpad({ onNext, config }: LaunchpadProps) {
  const [selectedMode, setSelectedMode] = useState<BacktestMode>(config.mode);
  const [symbol, setSymbol] = useState(config.symbol || 'BTC/USDT');
  const [timeframe, setTimeframe] = useState(config.timeframe || '1h');
  const [environment, setEnvironment] = useState(config.environment);
  const [capital, setCapital] = useState(config.capital.toString());
  const [leverage, setLeverage] = useState(config.leverage?.toString() || '10');
  const [riskPerTrade, setRiskPerTrade] = useState(config.riskPerTrade?.toString() || '2');
  const [maxPositionSize, setMaxPositionSize] = useState(config.maxPositionSize?.toString() || '99');
  const [useActiveTrades, setUseActiveTrades] = useState(config.useActiveTrades ?? true);
  const [exchange] = useState(config.exchange);

  const timeframes = ['15m', '1h', '4h', '1d'];

  const recentSearches = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT'];

  const handleNext = () => {
    if (!selectedMode) return;
    
    onNext({
      mode: selectedMode,
      symbol: selectedMode === 'single' ? symbol : undefined,
      timeframe,
      environment,
      capital: parseFloat(capital),
      leverage: parseFloat(leverage),
      riskPerTrade: parseFloat(riskPerTrade),
      maxPositionSize: parseFloat(maxPositionSize),
      useActiveTrades,
      exchange,
    });
  };

  return (
    <div className="min-h-screen flex items-center justify-center p-8">
      <div className="w-full max-w-6xl space-y-8">
        {/* Header */}
        <motion.div 
          initial={{ opacity: 0, y: -20 }}
          animate={{ opacity: 1, y: 0 }}
          className="text-center space-y-4"
        >
          <h1 className="text-5xl font-bold bg-gradient-to-r from-violet-400 via-purple-300 to-cyan-400 bg-clip-text text-transparent">
            Strategy Command Center
          </h1>
          <p className="text-slate-400 text-lg">Choose your backtest mode and configure your environment</p>
        </motion.div>

        {/* Backtest Mode Selector */}
        <motion.div 
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.1 }}
          className="grid md:grid-cols-2 gap-6"
        >
          {/* Single Pair Scout */}
          <button
            onClick={() => setSelectedMode('single')}
            className="group relative"
          >
            <div 
              className={`
                relative bg-slate-800/40 backdrop-blur-xl rounded-2xl p-8 border transition-all duration-300
                ${selectedMode === 'single' 
                  ? 'border-violet-500/50 shadow-[0_0_40px_rgba(139,92,246,0.3)]' 
                  : 'border-white/10 hover:border-violet-500/30'}
              `}
            >
              {selectedMode === 'single' && (
                <div className="absolute inset-0 bg-gradient-to-br from-violet-500/10 to-transparent rounded-2xl" />
              )}
              
              <div className="relative space-y-6">
                <div className="flex items-center gap-4">
                  <div className="p-4 bg-violet-500/20 rounded-xl">
                    <Target className="w-8 h-8 text-violet-400" />
                  </div>
                  <div className="text-left">
                    <h3 className="text-2xl font-bold text-white">Single Pair Scout</h3>
                    <p className="text-slate-400 text-sm">Deep dive into one trading pair</p>
                  </div>
                </div>

                {selectedMode === 'single' && (
                  <motion.div
                    initial={{ opacity: 0, height: 0 }}
                    animate={{ opacity: 1, height: 'auto' }}
                    className="space-y-4 pt-4 border-t border-white/10"
                  >
                    {/* Symbol Input */}
                    <div className="space-y-2">
                      <Label className="text-slate-300">Symbol</Label>
                      <Input
                        value={symbol}
                        onChange={(e) => setSymbol(e.target.value)}
                        placeholder="BTC/USDT"
                        className="bg-slate-900/50 border-white/10 text-white placeholder:text-slate-500 focus:border-violet-500/50"
                      />
                      <div className="flex gap-2 flex-wrap">
                        {recentSearches.map((search) => (
                          <button
                            key={search}
                            onClick={(e) => {
                              e.stopPropagation();
                              setSymbol(search);
                            }}
                            className="px-3 py-1 text-xs bg-slate-700/50 hover:bg-slate-700 text-slate-300 rounded-full transition-colors"
                          >
                            {search}
                          </button>
                        ))}
                      </div>
                    </div>

                    {/* Timeframe Pills */}
                    <div className="space-y-2">
                      <Label className="text-slate-300">Timeframe</Label>
                      <div className="flex gap-2">
                        {timeframes.map((tf) => (
                          <button
                            key={tf}
                            onClick={(e) => {
                              e.stopPropagation();
                              setTimeframe(tf);
                            }}
                            className={`
                              px-4 py-2 rounded-lg font-medium transition-all duration-200
                              ${timeframe === tf
                                ? 'bg-violet-500 text-white shadow-lg shadow-violet-500/50'
                                : 'bg-slate-700/50 text-slate-300 hover:bg-slate-700'}
                            `}
                          >
                            {tf}
                          </button>
                        ))}
                      </div>
                    </div>
                  </motion.div>
                )}
              </div>
            </div>
          </button>

          {/* Portfolio Batch */}
          <button
            onClick={() => setSelectedMode('batch')}
            className="group relative"
          >
            <div 
              className={`
                relative bg-slate-800/40 backdrop-blur-xl rounded-2xl p-8 border transition-all duration-300
                ${selectedMode === 'batch' 
                  ? 'border-cyan-500/50 shadow-[0_0_40px_rgba(6,182,212,0.3)]' 
                  : 'border-white/10 hover:border-cyan-500/30'}
              `}
            >
              {selectedMode === 'batch' && (
                <div className="absolute inset-0 bg-gradient-to-br from-cyan-500/10 to-transparent rounded-2xl" />
              )}
              
              <div className="relative space-y-6">
                <div className="flex items-center gap-4">
                  <div className="p-4 bg-cyan-500/20 rounded-xl">
                    <LayersIcon className="w-8 h-8 text-cyan-400" />
                  </div>
                  <div className="text-left">
                    <h3 className="text-2xl font-bold text-white">Portfolio Batch</h3>
                    <p className="text-slate-400 text-sm">Run across all pairs in symbols.txt</p>
                  </div>
                </div>

                {selectedMode === 'batch' && (
                  <motion.div
                    initial={{ opacity: 0, height: 0 }}
                    animate={{ opacity: 1, height: 'auto' }}
                    className="space-y-4 pt-4 border-t border-white/10"
                  >
                    {/* Timeframe Pills */}
                    <div className="space-y-2">
                      <Label className="text-slate-300">Timeframe</Label>
                      <div className="flex gap-2">
                        {timeframes.map((tf) => (
                          <button
                            key={tf}
                            onClick={(e) => {
                              e.stopPropagation();
                              setTimeframe(tf);
                            }}
                            className={`
                              px-4 py-2 rounded-lg font-medium transition-all duration-200
                              ${timeframe === tf
                                ? 'bg-cyan-500 text-white shadow-lg shadow-cyan-500/50'
                                : 'bg-slate-700/50 text-slate-300 hover:bg-slate-700'}
                            `}
                          >
                            {tf}
                          </button>
                        ))}
                      </div>
                    </div>

                    {/* File Preview */}
                    <div className="bg-slate-900/80 rounded-lg p-4 font-mono text-sm">
                      <div className="text-slate-500 mb-2"># symbols.txt</div>
                      <div className="text-cyan-400 space-y-1">
                        <div>BTC/USDT</div>
                        <div>ETH/USDT</div>
                        <div>SOL/USDT</div>
                        <div className="text-slate-600">... 12 more pairs</div>
                      </div>
                    </div>
                  </motion.div>
                )}
              </div>
            </div>
          </button>
        </motion.div>

        {/* Global Settings Panel */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.2 }}
          className="bg-slate-800/40 backdrop-blur-xl rounded-2xl p-8 border border-white/10"
        >
          <h3 className="text-xl font-bold text-white mb-6">Global Settings</h3>
          
          <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6 mb-6">
            {/* Environment Toggle */}
            <div className="space-y-3">
              <Label className="text-slate-300 flex items-center gap-2">
                <Server className="w-4 h-4" />
                Environment
              </Label>
              <div className="flex items-center gap-4 bg-slate-900/50 rounded-lg p-3">
                <Switch
                  checked={environment !== 'mock'}
                  onCheckedChange={(checked) => setEnvironment(checked ? 'paper' : 'mock')}
                />
                <div className="flex gap-2 text-sm">
                  <span className={environment === 'mock' ? 'text-violet-400 font-medium' : 'text-slate-500'}>Mock</span>
                  <span className="text-slate-600">/</span>
                  <span className={environment !== 'mock' ? 'text-violet-400 font-medium' : 'text-slate-500'}>Paper</span>
                </div>
              </div>
            </div>

            {/* Capital */}
            <div className="space-y-3">
              <Label className="text-slate-300 flex items-center gap-2">
                <DollarSign className="w-4 h-4" />
                Starting Capital
              </Label>
              <div className="relative">
                <span className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400 font-mono">$</span>
                <Input
                  type="number"
                  value={capital}
                  onChange={(e) => setCapital(e.target.value)}
                  className="bg-slate-900/50 border-white/10 text-white pl-8 font-mono"
                />
              </div>
            </div>

            {/* Exchange */}
            <div className="space-y-3">
              <Label className="text-slate-300">Exchange</Label>
              <div className="bg-slate-900/50 rounded-lg p-3 border border-white/10">
                <div className="text-white font-medium">{exchange}</div>
                <div className="text-xs text-slate-500">Futures (USDM)</div>
              </div>
            </div>
          </div>

          <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6">
            {/* Leverage */}
            <div className="space-y-3">
              <Label className="text-slate-300 flex items-center gap-2">
                <TrendingUp className="w-4 h-4" />
                Leverage
              </Label>
              <div className="space-y-2">
                <div className="flex items-center gap-3">
                  <Slider
                    value={[parseFloat(leverage)]}
                    onValueChange={(value) => setLeverage(value[0].toString())}
                    min={1}
                    max={20}
                    step={1}
                    className="flex-1"
                  />
                  <div className="w-16 text-right">
                    <span className="text-white font-mono font-bold">{leverage}x</span>
                  </div>
                </div>
              </div>
            </div>

            {/* Risk Per Trade */}
            <div className="space-y-3">
              <Label className="text-slate-300 flex items-center gap-2">
                <Shield className="w-4 h-4" />
                Risk Per Trade
              </Label>
              <div className="relative">
                <Input
                  type="number"
                  value={riskPerTrade}
                  onChange={(e) => setRiskPerTrade(e.target.value)}
                  className="bg-slate-900/50 border-white/10 text-white pr-8 font-mono"
                  step="0.1"
                />
                <span className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 font-mono">%</span>
              </div>
            </div>

            {/* Max Position Size */}
            <div className="space-y-3">
              <Label className="text-slate-300">Max Position Size</Label>
              <div className="relative">
                <Input
                  type="number"
                  value={maxPositionSize}
                  onChange={(e) => setMaxPositionSize(e.target.value)}
                  className="bg-slate-900/50 border-white/10 text-white pr-8 font-mono"
                />
                <span className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 font-mono">%</span>
              </div>
            </div>

            {/* Use Active Trades */}
            <div className="space-y-3">
              <Label className="text-slate-300 flex items-center gap-2">
                <Users className="w-4 h-4" />
                Use Active Trades
              </Label>
              <div className="flex items-center gap-3 bg-slate-900/50 rounded-lg p-3 h-[42px]">
                <Switch
                  checked={useActiveTrades}
                  onCheckedChange={setUseActiveTrades}
                />
                <span className={`text-sm ${useActiveTrades ? 'text-emerald-400' : 'text-slate-500'}`}>
                  {useActiveTrades ? 'Enabled' : 'Disabled'}
                </span>
              </div>
            </div>
          </div>
        </motion.div>

        {/* Action Button */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.3 }}
        >
          <button
            onClick={handleNext}
            disabled={!selectedMode}
            className={`
              w-full py-6 rounded-xl font-bold text-lg transition-all duration-300 flex items-center justify-center gap-3
              ${selectedMode
                ? 'bg-gradient-to-r from-violet-600 to-cyan-600 hover:from-violet-500 hover:to-cyan-500 text-white shadow-[0_0_40px_rgba(139,92,246,0.4)] hover:shadow-[0_0_60px_rgba(139,92,246,0.6)] active:scale-95'
                : 'bg-slate-800/50 text-slate-500 cursor-not-allowed'}
            `}
          >
            NEXT: CONFIGURE STRATEGY
            <ChevronRight className="w-6 h-6" />
          </button>
        </motion.div>
      </div>
    </div>
  );
}
