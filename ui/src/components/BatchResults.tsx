import { useState, useEffect } from 'react';
import { ChevronLeft, BarChart3, TrendingUp, TrendingDown, Activity, Award, ArrowUpRight, ArrowDownRight, Layers } from 'lucide-react';
import { motion } from 'motion/react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import { SymbolPerformance } from './ResultsDashboard';

interface Trade {
  id: number;
  entryTime: string;
  symbol: string;
  side: 'LONG' | 'SHORT';
  entryPrice: number;
  exitPrice: number;
  pnl: number;
  pnlPercent: number;
  exitReason: string;
}

interface BatchResultsProps {
  batchPerformance: SymbolPerformance[];
  selectedSymbol: string | null;
  onSelectSymbol: (symbol: string | null) => void;
  symbolTrades: Trade[];
  onSelectTrade: (trade: Trade) => void;
  onBack: () => void;
}

export function BatchResults({
  batchPerformance,
  selectedSymbol,
  onSelectSymbol,
  symbolTrades,
  onSelectTrade,
  onBack
}: BatchResultsProps) {
  // Calculate portfolio totals
  const totalPnl = batchPerformance.reduce((sum, p) => sum + p.pnl, 0);
  const portfolioReturn = (totalPnl / 10000) * 100;
  const avgDrawdown = batchPerformance.reduce((sum, p) => sum + p.drawdown, 0) / batchPerformance.length;
  const overallWinRate = batchPerformance.reduce((sum, p) => sum + (p.winRate * p.totalTrades), 0) /
                         batchPerformance.reduce((sum, p) => sum + p.totalTrades, 0);
  const totalTrades = batchPerformance.reduce((sum, p) => sum + p.totalTrades, 0);
  const profitableSymbols = batchPerformance.filter(p => p.pnl > 0).length;

  // Animated counters
  const [displayTotalPnl, setDisplayTotalPnl] = useState(0);
  const [displayPortfolioReturn, setDisplayPortfolioReturn] = useState(0);

  useEffect(() => {
    const duration = 1500;
    const steps = 60;
    const stepDuration = duration / steps;

    let currentStep = 0;
    const interval = setInterval(() => {
      currentStep++;
      const progress = currentStep / steps;
      setDisplayTotalPnl(totalPnl * progress);
      setDisplayPortfolioReturn(portfolioReturn * progress);

      if (currentStep >= steps) {
        clearInterval(interval);
      }
    }, stepDuration);

    return () => clearInterval(interval);
  }, [totalPnl, portfolioReturn]);

  // Generate portfolio equity curve (cumulative)
  const portfolioEquityCurve = batchPerformance
    .sort((a, b) => b.returnPercent - a.returnPercent)
    .reduce((acc, perf, index) => {
      const prevEquity = index === 0 ? 10000 : acc[index - 1].equity;
      acc.push({
        index: index + 1,
        equity: prevEquity + perf.pnl,
        symbol: perf.symbol,
      });
      return acc;
    }, [] as { index: number; equity: number; symbol: string }[]);

  return (
    <div className="min-h-screen flex">
      {/* Sidebar Navigation */}
      <motion.div
        initial={{ x: -300, opacity: 0 }}
        animate={{ x: 0, opacity: 1 }}
        className="w-80 bg-slate-900/50 backdrop-blur-xl border-r border-white/10 flex flex-col"
      >
        {/* Sidebar Header */}
        <div className="p-6 border-b border-white/10">
          <button
            onClick={onBack}
            className="mb-4 p-2 bg-slate-800/40 border border-white/10 hover:border-violet-500/30 text-slate-300 hover:text-white rounded-lg transition-all w-full flex items-center gap-2"
          >
            <ChevronLeft className="w-4 h-4" />
            Back to Strategy Lab
          </button>
          <div className="flex items-center gap-3 mb-2">
            <div className="p-2 bg-violet-500/20 rounded-lg">
              <Layers className="w-5 h-5 text-violet-400" />
            </div>
            <h2 className="text-xl font-bold text-white">RSI Bot Batch</h2>
          </div>
          <p className="text-sm text-slate-400">Portfolio backtest results</p>
        </div>

        {/* Overview Button */}
        <div className="p-4">
          <button
            onClick={() => onSelectSymbol(null)}
            className={`
              w-full px-4 py-3 rounded-lg transition-all flex items-center gap-3
              ${!selectedSymbol
                ? 'bg-gradient-to-r from-violet-600 to-purple-600 text-white shadow-lg shadow-violet-500/30'
                : 'bg-slate-800/40 text-slate-300 hover:bg-slate-800'}
            `}
          >
            <BarChart3 className="w-5 h-5" />
            <span className="font-medium">Portfolio Overview</span>
          </button>
        </div>

        {/* Symbol List */}
        <div className="flex-1 overflow-y-auto px-4 pb-4 space-y-2">
          {batchPerformance.map((perf) => (
            <button
              key={perf.symbol}
              onClick={() => onSelectSymbol(perf.symbol)}
              className={`
                w-full px-4 py-3 rounded-lg transition-all text-left
                ${selectedSymbol === perf.symbol
                  ? 'bg-slate-800 border border-violet-500/30 shadow-lg'
                  : 'bg-slate-800/20 hover:bg-slate-800/40 border border-transparent'}
              `}
            >
              <div className="flex items-center justify-between mb-1">
                <span className="text-white font-medium text-sm">{perf.symbol}</span>
                <span className={`
                  text-xs font-mono px-2 py-0.5 rounded
                  ${perf.returnPercent > 0
                    ? 'bg-emerald-500/20 text-emerald-400'
                    : 'bg-rose-500/20 text-rose-400'}
                `}>
                  {perf.returnPercent > 0 ? '+' : ''}{perf.returnPercent.toFixed(1)}%
                </span>
              </div>
              <div className="flex items-center justify-between text-xs">
                <span className="text-slate-400">{perf.totalTrades} trades</span>
                <span className="text-slate-400">{perf.winRate.toFixed(0)}% WR</span>
              </div>
            </button>
          ))}
        </div>
      </motion.div>

      {/* Main Content */}
      <div className="flex-1 overflow-y-auto">
        {!selectedSymbol ? (
          // Portfolio Overview
          <div className="p-8">
            <div className="max-w-[1400px] mx-auto space-y-6">
              {/* Header */}
              <motion.div
                initial={{ opacity: 0, y: -20 }}
                animate={{ opacity: 1, y: 0 }}
              >
                <h1 className="text-3xl font-bold bg-gradient-to-r from-violet-400 to-cyan-400 bg-clip-text text-transparent">
                  Portfolio Overview
                </h1>
                <p className="text-slate-400 mt-1">Aggregated performance across all trading pairs</p>
              </motion.div>

              {/* Portfolio Stats */}
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
                <motion.div
                  initial={{ opacity: 0, y: 20 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: 0.1 }}
                  className="bg-slate-800/40 backdrop-blur-xl rounded-2xl p-6 border border-white/10 relative overflow-hidden"
                >
                  <div className="absolute top-0 right-0 w-32 h-32 bg-gradient-to-br from-emerald-500/20 to-transparent rounded-full blur-2xl" />
                  <div className="relative">
                    <div className="flex items-center justify-between mb-3">
                      <h3 className="text-slate-400 text-sm">Total Net Profit</h3>
                      <TrendingUp className="w-5 h-5 text-emerald-400" />
                    </div>
                    <div className="text-3xl font-bold text-emerald-400 font-mono">
                      ${displayTotalPnl.toFixed(2)}
                    </div>
                    <div className="text-slate-400 text-sm mt-1">
                      Across {batchPerformance.length} pairs
                    </div>
                  </div>
                </motion.div>

                <motion.div
                  initial={{ opacity: 0, y: 20 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: 0.15 }}
                  className="bg-slate-800/40 backdrop-blur-xl rounded-2xl p-6 border border-white/10 relative overflow-hidden"
                >
                  <div className="absolute top-0 right-0 w-32 h-32 bg-gradient-to-br from-violet-500/20 to-transparent rounded-full blur-2xl" />
                  <div className="relative">
                    <div className="flex items-center justify-between mb-3">
                      <h3 className="text-slate-400 text-sm">Portfolio Return</h3>
                      <Activity className="w-5 h-5 text-violet-400" />
                    </div>
                    <div className="text-3xl font-bold text-white font-mono">
                      +{displayPortfolioReturn.toFixed(2)}%
                    </div>
                    <div className="text-slate-400 text-sm mt-1">
                      {profitableSymbols}/{batchPerformance.length} profitable
                    </div>
                  </div>
                </motion.div>

                <motion.div
                  initial={{ opacity: 0, y: 20 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: 0.2 }}
                  className="bg-slate-800/40 backdrop-blur-xl rounded-2xl p-6 border border-white/10 relative overflow-hidden"
                >
                  <div className="absolute top-0 right-0 w-32 h-32 bg-gradient-to-br from-cyan-500/20 to-transparent rounded-full blur-2xl" />
                  <div className="relative">
                    <div className="flex items-center justify-between mb-3">
                      <h3 className="text-slate-400 text-sm">Avg Drawdown</h3>
                      <TrendingDown className="w-5 h-5 text-cyan-400" />
                    </div>
                    <div className="text-3xl font-bold text-white font-mono">
                      {avgDrawdown.toFixed(2)}%
                    </div>
                    <div className="text-slate-400 text-sm mt-1">
                      Portfolio risk metric
                    </div>
                  </div>
                </motion.div>

                <motion.div
                  initial={{ opacity: 0, y: 20 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: 0.25 }}
                  className="bg-slate-800/40 backdrop-blur-xl rounded-2xl p-6 border border-white/10 relative overflow-hidden"
                >
                  <div className="absolute top-0 right-0 w-32 h-32 bg-gradient-to-br from-rose-500/20 to-transparent rounded-full blur-2xl" />
                  <div className="relative">
                    <div className="flex items-center justify-between mb-3">
                      <h3 className="text-slate-400 text-sm">Overall Win Rate</h3>
                      <Award className="w-5 h-5 text-rose-400" />
                    </div>
                    <div className="text-3xl font-bold text-white font-mono">
                      {overallWinRate.toFixed(1)}%
                    </div>
                    <div className="text-slate-400 text-sm mt-1">
                      {totalTrades} total trades
                    </div>
                  </div>
                </motion.div>
              </div>

              {/* Portfolio Equity Curve */}
              <motion.div
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.3 }}
                className="bg-slate-800/40 backdrop-blur-xl rounded-2xl p-6 border border-white/10"
              >
                <div className="mb-6">
                  <h3 className="font-bold text-white text-lg">Portfolio Equity Curve</h3>
                  <p className="text-sm text-slate-400">Cumulative balance across all pairs</p>
                </div>
                <ResponsiveContainer width="100%" height={350}>
                  <LineChart data={portfolioEquityCurve}>
                    <defs>
                      <linearGradient id="portfolioGradient" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor="#8B5CF6" stopOpacity={0.4} />
                        <stop offset="100%" stopColor="#8B5CF6" stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke="#334155" opacity={0.3} />
                    <XAxis
                      dataKey="index"
                      stroke="#64748b"
                      tick={{ fill: '#94a3b8', fontSize: 11 }}
                      label={{ value: 'Trading Pairs', fill: '#64748b', position: 'insideBottom', offset: -5 }}
                    />
                    <YAxis
                      stroke="#64748b"
                      tick={{ fill: '#94a3b8', fontSize: 11 }}
                      tickFormatter={(value) => `$${(value / 1000).toFixed(1)}k`}
                    />
                    <Tooltip
                      contentStyle={{
                        backgroundColor: 'rgba(15, 23, 42, 0.95)',
                        border: '1px solid rgba(255, 255, 255, 0.1)',
                        borderRadius: '8px',
                        padding: '12px',
                      }}
                      labelStyle={{ color: '#94a3b8', fontSize: '12px' }}
                      itemStyle={{ color: '#e2e8f0', fontSize: '12px', fontFamily: 'monospace' }}
                      formatter={(value: number, name: string, props: any) => [
                        `$${value.toFixed(2)}`,
                        props.payload.symbol
                      ]}
                    />
                    <Line
                      type="monotone"
                      dataKey="equity"
                      stroke="#8B5CF6"
                      strokeWidth={3}
                      fill="url(#portfolioGradient)"
                      dot={{ fill: '#8B5CF6', r: 4 }}
                    />
                  </LineChart>
                </ResponsiveContainer>
              </motion.div>

              {/* Performance Table */}
              <motion.div
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.35 }}
                className="bg-slate-800/40 backdrop-blur-xl rounded-2xl border border-white/10 overflow-hidden"
              >
                <div className="p-6 border-b border-white/10">
                  <h3 className="font-bold text-white text-lg">Symbol Performance Breakdown</h3>
                  <p className="text-sm text-slate-400 mt-1">Click a symbol in the sidebar to view detailed trades</p>
                </div>

                <div className="overflow-x-auto">
                  <table className="w-full">
                    <thead>
                      <tr className="border-b border-white/10 bg-slate-900/30">
                        <th className="px-6 py-4 text-left text-xs font-medium text-slate-400 uppercase tracking-wider">Symbol</th>
                        <th className="px-6 py-4 text-right text-xs font-medium text-slate-400 uppercase tracking-wider">PnL ($)</th>
                        <th className="px-6 py-4 text-right text-xs font-medium text-slate-400 uppercase tracking-wider">Return (%)</th>
                        <th className="px-6 py-4 text-right text-xs font-medium text-slate-400 uppercase tracking-wider">Drawdown</th>
                        <th className="px-6 py-4 text-right text-xs font-medium text-slate-400 uppercase tracking-wider">Win Rate</th>
                        <th className="px-6 py-4 text-right text-xs font-medium text-slate-400 uppercase tracking-wider">Trades</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-white/5">
                      {batchPerformance.map((perf, index) => (
                        <motion.tr
                          key={perf.symbol}
                          initial={{ opacity: 0, x: -20 }}
                          animate={{ opacity: 1, x: 0 }}
                          transition={{ delay: 0.35 + index * 0.02 }}
                          onClick={() => onSelectSymbol(perf.symbol)}
                          className="hover:bg-slate-700/30 cursor-pointer transition-colors"
                        >
                          <td className="px-6 py-4 whitespace-nowrap">
                            <div className="font-bold text-white">{perf.symbol}</div>
                          </td>
                          <td className="px-6 py-4 whitespace-nowrap text-right font-mono">
                            <div className={perf.pnl > 0 ? 'text-emerald-400' : 'text-rose-400'}>
                              {perf.pnl > 0 ? '+' : ''}${perf.pnl.toFixed(2)}
                            </div>
                          </td>
                          <td className="px-6 py-4 whitespace-nowrap text-right font-mono">
                            <div className={perf.returnPercent > 0 ? 'text-emerald-400' : 'text-rose-400'}>
                              {perf.returnPercent > 0 ? '+' : ''}{perf.returnPercent.toFixed(2)}%
                            </div>
                          </td>
                          <td className="px-6 py-4 whitespace-nowrap text-right font-mono text-slate-300">
                            {perf.drawdown.toFixed(2)}%
                          </td>
                          <td className="px-6 py-4 whitespace-nowrap text-right font-mono text-white">
                            {perf.winRate.toFixed(1)}%
                          </td>
                          <td className="px-6 py-4 whitespace-nowrap text-right">
                            <div className="text-slate-300 font-mono">{perf.totalTrades}</div>
                            <div className="text-xs text-slate-500">{perf.wins}W / {perf.losses}L</div>
                          </td>
                        </motion.tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </motion.div>
            </div>
          </div>
        ) : (
          // Symbol Detail View
          <div className="p-8">
            <div className="max-w-[1400px] mx-auto space-y-6">
              {/* Symbol Header */}
              <motion.div
                initial={{ opacity: 0, y: -20 }}
                animate={{ opacity: 1, y: 0 }}
              >
                <h1 className="text-3xl font-bold text-white">{selectedSymbol}</h1>
                <p className="text-slate-400 mt-1">Individual pair backtest results</p>
              </motion.div>

              {/* Symbol Stats */}
              {(() => {
                const perf = batchPerformance.find(p => p.symbol === selectedSymbol);
                if (!perf) return null;

                return (
                  <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
                    <motion.div
                      initial={{ opacity: 0, y: 20 }}
                      animate={{ opacity: 1, y: 0 }}
                      className="bg-slate-800/40 backdrop-blur-xl rounded-xl p-6 border border-white/10"
                    >
                      <h4 className="text-xs text-slate-400 mb-2">Net PnL</h4>
                      <div className={`text-2xl font-bold font-mono ${perf.pnl > 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                        {perf.pnl > 0 ? '+' : ''}${perf.pnl.toFixed(2)}
                      </div>
                    </motion.div>

                    <motion.div
                      initial={{ opacity: 0, y: 20 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ delay: 0.05 }}
                      className="bg-slate-800/40 backdrop-blur-xl rounded-xl p-6 border border-white/10"
                    >
                      <h4 className="text-xs text-slate-400 mb-2">Return</h4>
                      <div className={`text-2xl font-bold font-mono ${perf.returnPercent > 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                        {perf.returnPercent > 0 ? '+' : ''}{perf.returnPercent.toFixed(2)}%
                      </div>
                    </motion.div>

                    <motion.div
                      initial={{ opacity: 0, y: 20 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ delay: 0.1 }}
                      className="bg-slate-800/40 backdrop-blur-xl rounded-xl p-6 border border-white/10"
                    >
                      <h4 className="text-xs text-slate-400 mb-2">Win Rate</h4>
                      <div className="text-2xl font-bold font-mono text-white">
                        {perf.winRate.toFixed(1)}%
                      </div>
                    </motion.div>

                    <motion.div
                      initial={{ opacity: 0, y: 20 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ delay: 0.15 }}
                      className="bg-slate-800/40 backdrop-blur-xl rounded-xl p-6 border border-white/10"
                    >
                      <h4 className="text-xs text-slate-400 mb-2">Drawdown</h4>
                      <div className="text-2xl font-bold font-mono text-rose-400">
                        {perf.drawdown.toFixed(2)}%
                      </div>
                    </motion.div>
                  </div>
                );
              })()}

              {/* Trades Table */}
              <motion.div
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.2 }}
                className="bg-slate-800/40 backdrop-blur-xl rounded-2xl border border-white/10 overflow-hidden"
              >
                <div className="p-6 border-b border-white/10">
                  <h3 className="font-bold text-white text-lg">Trade History</h3>
                  <p className="text-sm text-slate-400 mt-1">Click any trade to view chart details</p>
                </div>

                <div className="overflow-x-auto">
                  <table className="w-full">
                    <thead>
                      <tr className="border-b border-white/10 bg-slate-900/30">
                        <th className="px-6 py-4 text-left text-xs font-medium text-slate-400 uppercase tracking-wider">ID</th>
                        <th className="px-6 py-4 text-left text-xs font-medium text-slate-400 uppercase tracking-wider">Entry Time</th>
                        <th className="px-6 py-4 text-left text-xs font-medium text-slate-400 uppercase tracking-wider">Side</th>
                        <th className="px-6 py-4 text-right text-xs font-medium text-slate-400 uppercase tracking-wider">Entry $</th>
                        <th className="px-6 py-4 text-right text-xs font-medium text-slate-400 uppercase tracking-wider">Exit $</th>
                        <th className="px-6 py-4 text-right text-xs font-medium text-slate-400 uppercase tracking-wider">PnL</th>
                        <th className="px-6 py-4 text-left text-xs font-medium text-slate-400 uppercase tracking-wider">Exit Reason</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-white/5">
                      {symbolTrades.map((trade, index) => (
                        <motion.tr
                          key={trade.id}
                          initial={{ opacity: 0, x: -20 }}
                          animate={{ opacity: 1, x: 0 }}
                          transition={{ delay: 0.2 + index * 0.01 }}
                          onClick={() => onSelectTrade(trade)}
                          className="hover:bg-slate-700/30 cursor-pointer transition-colors"
                        >
                          <td className="px-6 py-4 whitespace-nowrap text-sm text-slate-400 font-mono">
                            #{trade.id}
                          </td>
                          <td className="px-6 py-4 whitespace-nowrap text-sm text-slate-300 font-mono">
                            {new Date(trade.entryTime).toLocaleString('en-US', {
                              month: 'short',
                              day: 'numeric',
                              hour: '2-digit',
                              minute: '2-digit'
                            })}
                          </td>
                          <td className="px-6 py-4 whitespace-nowrap">
                            <span className={`
                              inline-flex items-center gap-1 px-2 py-1 rounded-md text-xs font-medium
                              ${trade.side === 'LONG'
                                ? 'bg-emerald-500/20 text-emerald-400'
                                : 'bg-rose-500/20 text-rose-400'}
                            `}>
                              {trade.side === 'LONG' ? <ArrowUpRight className="w-3 h-3" /> : <ArrowDownRight className="w-3 h-3" />}
                              {trade.side}
                            </span>
                          </td>
                          <td className="px-6 py-4 whitespace-nowrap text-sm text-right text-slate-300 font-mono">
                            ${trade.entryPrice.toFixed(2)}
                          </td>
                          <td className="px-6 py-4 whitespace-nowrap text-sm text-right text-slate-300 font-mono">
                            ${trade.exitPrice.toFixed(2)}
                          </td>
                          <td className="px-6 py-4 whitespace-nowrap text-sm text-right font-mono">
                            <div className={trade.pnl > 0 ? 'text-emerald-400' : 'text-rose-400'}>
                              {trade.pnl > 0 ? '+' : ''}${trade.pnl.toFixed(2)}
                            </div>
                            <div className={`text-xs ${trade.pnl > 0 ? 'text-emerald-400/70' : 'text-rose-400/70'}`}>
                              {trade.pnl > 0 ? '+' : ''}{trade.pnlPercent.toFixed(2)}%
                            </div>
                          </td>
                          <td className="px-6 py-4 whitespace-nowrap">
                            <span className={`
                              inline-flex px-2 py-1 rounded-full text-xs font-medium
                              ${trade.exitReason === 'TP1' || trade.exitReason === 'TP2'
                                ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30'
                                : trade.exitReason === 'Stop Loss'
                                ? 'bg-rose-500/20 text-rose-400 border border-rose-500/30'
                                : 'bg-violet-500/20 text-violet-400 border border-violet-500/30'}
                            `}>
                              {trade.exitReason}
                            </span>
                          </td>
                        </motion.tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </motion.div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
