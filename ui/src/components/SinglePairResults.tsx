import { useState, useEffect } from 'react';
import { TrendingUp, TrendingDown, Activity, Award, ChevronLeft, ArrowUpRight, ArrowDownRight, PieChart as PieChartIcon, TrendingUpIcon } from 'lucide-react';
import { motion } from 'motion/react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, PieChart, Pie, Cell } from 'recharts';

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

interface SinglePairResultsProps {
  trades: Trade[];
  symbol: string;
  onSelectTrade: (trade: Trade) => void;
  onBack: () => void;
}

export function SinglePairResults({ trades, symbol, onSelectTrade, onBack }: SinglePairResultsProps) {
  // Calculate metrics
  const netPnl = trades.reduce((sum, t) => sum + t.pnl, 0);
  const winningTrades = trades.filter(t => t.pnl > 0);
  const losingTrades = trades.filter(t => t.pnl <= 0);
  const winRate = (winningTrades.length / trades.length) * 100;
  const maxDrawdown = 2.78;
  const sharpeRatio = 0.23;
  const sortinoRatio = 0.31;
  const calmarRatio = 4.79;
  const volatility = 9.86;
  
  // Calculate additional stats
  const avgWin = winningTrades.reduce((sum, t) => sum + t.pnl, 0) / winningTrades.length;
  const avgLoss = Math.abs(losingTrades.reduce((sum, t) => sum + t.pnl, 0) / losingTrades.length);
  const largestWin = Math.max(...winningTrades.map(t => t.pnl));
  const largestLoss = Math.min(...losingTrades.map(t => t.pnl));
  const grossProfit = winningTrades.reduce((sum, t) => sum + t.pnl, 0);
  const grossLoss = Math.abs(losingTrades.reduce((sum, t) => sum + t.pnl, 0));
  const profitFactor = grossProfit / grossLoss;
  const expectancy = (winRate / 100) * avgWin - ((100 - winRate) / 100) * avgLoss;
  const avgHoldTime = 7.1; // hours
  
  // Consecutive wins/losses
  let maxConsecWins = 0;
  let maxConsecLosses = 0;
  let currentConsecWins = 0;
  let currentConsecLosses = 0;
  
  trades.forEach(trade => {
    if (trade.pnl > 0) {
      currentConsecWins++;
      currentConsecLosses = 0;
      maxConsecWins = Math.max(maxConsecWins, currentConsecWins);
    } else {
      currentConsecLosses++;
      currentConsecWins = 0;
      maxConsecLosses = Math.max(maxConsecLosses, currentConsecLosses);
    }
  });

  // Animated counters
  const [displayNetPnl, setDisplayNetPnl] = useState(0);
  const [displayWinRate, setDisplayWinRate] = useState(0);

  useEffect(() => {
    const duration = 1500;
    const steps = 60;
    const stepDuration = duration / steps;

    let currentStep = 0;
    const interval = setInterval(() => {
      currentStep++;
      const progress = currentStep / steps;
      setDisplayNetPnl(netPnl * progress);
      setDisplayWinRate(winRate * progress);

      if (currentStep >= steps) {
        clearInterval(interval);
      }
    }, stepDuration);

    return () => clearInterval(interval);
  }, [netPnl, winRate]);

  // Generate equity curve
  const equityCurve = trades
    .sort((a, b) => new Date(a.entryTime).getTime() - new Date(b.entryTime).getTime())
    .reduce((acc, trade, index) => {
      const prevEquity = index === 0 ? 10000 : acc[index - 1].equity;
      acc.push({
        trade: index + 1,
        equity: prevEquity + trade.pnl,
        date: new Date(trade.entryTime).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
      });
      return acc;
    }, [] as { trade: number; equity: number; date: string }[]);

  // Exit reasons distribution
  const exitReasonCounts = trades.reduce((acc, trade) => {
    acc[trade.exitReason] = (acc[trade.exitReason] || 0) + 1;
    return acc;
  }, {} as Record<string, number>);

  const exitReasonData = Object.entries(exitReasonCounts).map(([name, value]) => ({
    name,
    value,
  }));

  const COLORS = {
    'TP1': '#10B981',
    'TP2': '#34D399',
    'Stop Loss': '#F43F5E',
    'Lock Profit': '#8B5CF6',
    'Time Exit': '#06B6D4',
  };

  return (
    <div className="min-h-screen p-8">
      <div className="max-w-[1800px] mx-auto space-y-6">
        {/* Header */}
        <motion.div
          initial={{ opacity: 0, y: -20 }}
          animate={{ opacity: 1, y: 0 }}
          className="flex items-center justify-between"
        >
          <div className="flex items-center gap-4">
            <button
              onClick={onBack}
              className="p-2 bg-slate-800/40 backdrop-blur-xl border border-white/10 hover:border-violet-500/30 text-slate-300 hover:text-white rounded-lg transition-all"
            >
              <ChevronLeft className="w-5 h-5" />
            </button>
            <div>
              <h1 className="text-3xl font-bold bg-gradient-to-r from-violet-400 to-cyan-400 bg-clip-text text-transparent">
                Backtest Results: {symbol}
              </h1>
              <p className="text-slate-400 text-sm mt-1">Performance analysis & trade history</p>
            </div>
          </div>
          
          <div className="flex items-center gap-3">
            <div className="bg-slate-800/40 backdrop-blur-xl rounded-lg px-4 py-2 border border-white/10">
              <div className="text-xs text-slate-400">Total Trades</div>
              <div className="text-xl font-bold text-white font-mono">{trades.length}</div>
            </div>
          </div>
        </motion.div>

        {/* Hero Stats */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.1 }}
            className="bg-slate-800/40 backdrop-blur-xl rounded-2xl p-6 border border-white/10 relative overflow-hidden group"
          >
            <div className="absolute top-0 right-0 w-32 h-32 bg-gradient-to-br from-emerald-500/20 to-transparent rounded-full blur-2xl" />
            <div className="relative">
              <div className="flex items-center justify-between mb-3">
                <h3 className="text-slate-400 text-sm">Net Profit/Loss</h3>
                <TrendingUp className="w-5 h-5 text-emerald-400" />
              </div>
              <div className="text-3xl font-bold text-emerald-400 font-mono">
                +${displayNetPnl.toFixed(2)}
              </div>
              <div className="text-emerald-400 text-sm mt-1 font-mono">
                +{((displayNetPnl / 10000) * 100).toFixed(2)}%
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
                <h3 className="text-slate-400 text-sm">Win Rate</h3>
                <Award className="w-5 h-5 text-violet-400" />
              </div>
              <div className="text-3xl font-bold text-white font-mono">
                {displayWinRate.toFixed(1)}%
              </div>
              <div className="text-slate-400 text-sm mt-1">
                {winningTrades.length}W / {losingTrades.length}L
              </div>
            </div>
          </motion.div>

          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.2 }}
            className="bg-slate-800/40 backdrop-blur-xl rounded-2xl p-6 border border-white/10 relative overflow-hidden"
          >
            <div className="absolute top-0 right-0 w-32 h-32 bg-gradient-to-br from-rose-500/20 to-transparent rounded-full blur-2xl" />
            <div className="relative">
              <div className="flex items-center justify-between mb-3">
                <h3 className="text-slate-400 text-sm">Max Drawdown</h3>
                <TrendingDown className="w-5 h-5 text-rose-400" />
              </div>
              <div className="text-3xl font-bold text-rose-400 font-mono">
                -{maxDrawdown}%
              </div>
              <div className="text-slate-400 text-sm mt-1">
                Peak to trough
              </div>
            </div>
          </motion.div>

          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.25 }}
            className="bg-slate-800/40 backdrop-blur-xl rounded-2xl p-6 border border-white/10 relative overflow-hidden"
          >
            <div className="absolute top-0 right-0 w-32 h-32 bg-gradient-to-br from-cyan-500/20 to-transparent rounded-full blur-2xl" />
            <div className="relative">
              <div className="flex items-center justify-between mb-3">
                <h3 className="text-slate-400 text-sm">Sharpe Ratio</h3>
                <Activity className="w-5 h-5 text-cyan-400" />
              </div>
              <div className="text-3xl font-bold text-white font-mono">
                {sharpeRatio}
              </div>
              <div className="text-slate-400 text-sm mt-1">
                Risk-adjusted return
              </div>
            </div>
          </motion.div>
        </div>

        {/* Additional Risk Metrics */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.3 }}
            className="bg-slate-800/40 backdrop-blur-xl rounded-xl p-4 border border-white/10"
          >
            <h4 className="text-xs text-slate-400 mb-2">Sortino Ratio</h4>
            <div className="text-xl font-bold text-white font-mono">
              {sortinoRatio}
            </div>
          </motion.div>

          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.32 }}
            className="bg-slate-800/40 backdrop-blur-xl rounded-xl p-4 border border-white/10"
          >
            <h4 className="text-xs text-slate-400 mb-2">Calmar Ratio</h4>
            <div className="text-xl font-bold text-white font-mono">
              {calmarRatio.toFixed(2)}
            </div>
          </motion.div>

          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.34 }}
            className="bg-slate-800/40 backdrop-blur-xl rounded-xl p-4 border border-white/10"
          >
            <h4 className="text-xs text-slate-400 mb-2">Volatility</h4>
            <div className="text-xl font-bold text-white font-mono">
              {volatility.toFixed(2)}%
            </div>
          </motion.div>

          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.36 }}
            className="bg-slate-800/40 backdrop-blur-xl rounded-xl p-4 border border-white/10"
          >
            <h4 className="text-xs text-slate-400 mb-2">Profit Factor</h4>
            <div className="text-xl font-bold text-white font-mono">
              {profitFactor.toFixed(2)}
            </div>
          </motion.div>

          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.38 }}
            className="bg-slate-800/40 backdrop-blur-xl rounded-xl p-4 border border-white/10"
          >
            <h4 className="text-xs text-slate-400 mb-2">Expectancy</h4>
            <div className="text-xl font-bold text-cyan-400 font-mono">
              ${expectancy.toFixed(2)}
            </div>
          </motion.div>

          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.40 }}
            className="bg-slate-800/40 backdrop-blur-xl rounded-xl p-4 border border-white/10"
          >
            <h4 className="text-xs text-slate-400 mb-2">Avg Hold Time</h4>
            <div className="text-xl font-bold text-white font-mono">
              {avgHoldTime.toFixed(1)}h
            </div>
          </motion.div>
        </div>

        {/* Win/Loss Stats */}
        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-8 gap-4">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.35 }}
            className="bg-slate-800/40 backdrop-blur-xl rounded-xl p-4 border border-white/10"
          >
            <h4 className="text-xs text-slate-400 mb-2">Avg Win</h4>
            <div className="text-lg font-bold text-emerald-400 font-mono">
              +${avgWin.toFixed(2)}
            </div>
          </motion.div>

          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.37 }}
            className="bg-slate-800/40 backdrop-blur-xl rounded-xl p-4 border border-white/10"
          >
            <h4 className="text-xs text-slate-400 mb-2">Avg Loss</h4>
            <div className="text-lg font-bold text-rose-400 font-mono">
              -${avgLoss.toFixed(2)}
            </div>
          </motion.div>

          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.39 }}
            className="bg-slate-800/40 backdrop-blur-xl rounded-xl p-4 border border-white/10"
          >
            <h4 className="text-xs text-slate-400 mb-2">Largest Win</h4>
            <div className="text-lg font-bold text-emerald-400 font-mono">
              +${largestWin.toFixed(2)}
            </div>
          </motion.div>

          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.41 }}
            className="bg-slate-800/40 backdrop-blur-xl rounded-xl p-4 border border-white/10"
          >
            <h4 className="text-xs text-slate-400 mb-2">Largest Loss</h4>
            <div className="text-lg font-bold text-rose-400 font-mono">
              ${largestLoss.toFixed(2)}
            </div>
          </motion.div>

          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.43 }}
            className="bg-slate-800/40 backdrop-blur-xl rounded-xl p-4 border border-white/10"
          >
            <h4 className="text-xs text-slate-400 mb-2">Max Consec. Wins</h4>
            <div className="text-lg font-bold text-white font-mono">
              {maxConsecWins}
            </div>
          </motion.div>

          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.45 }}
            className="bg-slate-800/40 backdrop-blur-xl rounded-xl p-4 border border-white/10"
          >
            <h4 className="text-xs text-slate-400 mb-2">Max Consec. Losses</h4>
            <div className="text-lg font-bold text-white font-mono">
              {maxConsecLosses}
            </div>
          </motion.div>

          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.47 }}
            className="bg-slate-800/40 backdrop-blur-xl rounded-xl p-4 border border-white/10"
          >
            <h4 className="text-xs text-slate-400 mb-2">Gross Profit</h4>
            <div className="text-lg font-bold text-emerald-400 font-mono">
              ${grossProfit.toFixed(2)}
            </div>
          </motion.div>

          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.49 }}
            className="bg-slate-800/40 backdrop-blur-xl rounded-xl p-4 border border-white/10"
          >
            <h4 className="text-xs text-slate-400 mb-2">Gross Loss</h4>
            <div className="text-lg font-bold text-rose-400 font-mono">
              ${grossLoss.toFixed(2)}
            </div>
          </motion.div>
        </div>

        {/* Charts Row */}
        <div className="grid lg:grid-cols-2 gap-6">
          {/* Equity Curve */}
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.4 }}
            className="bg-slate-800/40 backdrop-blur-xl rounded-2xl p-6 border border-white/10"
          >
            <div className="flex items-center gap-3 mb-6">
              <TrendingUpIcon className="w-5 h-5 text-violet-400" />
              <div>
                <h3 className="font-bold text-white">Portfolio Equity Curve</h3>
                <p className="text-xs text-slate-400">Account balance over time</p>
              </div>
            </div>
            <ResponsiveContainer width="100%" height={300}>
              <LineChart data={equityCurve}>
                <defs>
                  <linearGradient id="equityGradient" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#8B5CF6" stopOpacity={0.4} />
                    <stop offset="100%" stopColor="#8B5CF6" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#334155" opacity={0.3} />
                <XAxis 
                  dataKey="trade" 
                  stroke="#64748b" 
                  tick={{ fill: '#94a3b8', fontSize: 11 }}
                  label={{ value: 'Trade #', fill: '#64748b', position: 'insideBottom', offset: -5 }}
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
                  formatter={(value: number) => [`$${value.toFixed(2)}`, 'Balance']}
                />
                <Line 
                  type="monotone" 
                  dataKey="equity" 
                  stroke="#8B5CF6" 
                  strokeWidth={3}
                  fill="url(#equityGradient)"
                  dot={false}
                />
              </LineChart>
            </ResponsiveContainer>
          </motion.div>

          {/* Exit Reasons Distribution */}
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.45 }}
            className="bg-slate-800/40 backdrop-blur-xl rounded-2xl p-6 border border-white/10"
          >
            <div className="flex items-center gap-3 mb-6">
              <PieChartIcon className="w-5 h-5 text-cyan-400" />
              <div>
                <h3 className="font-bold text-white">Exit Reason Distribution</h3>
                <p className="text-xs text-slate-400">How trades were closed</p>
              </div>
            </div>
            <div className="flex items-center gap-8">
              <ResponsiveContainer width="60%" height={300}>
                <PieChart>
                  <Pie
                    data={exitReasonData}
                    cx="50%"
                    cy="50%"
                    innerRadius={60}
                    outerRadius={100}
                    paddingAngle={2}
                    dataKey="value"
                  >
                    {exitReasonData.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={COLORS[entry.name as keyof typeof COLORS] || '#64748b'} />
                    ))}
                  </Pie>
                  <Tooltip
                    contentStyle={{
                      backgroundColor: 'rgba(15, 23, 42, 0.95)',
                      border: '1px solid rgba(255, 255, 255, 0.1)',
                      borderRadius: '8px',
                      padding: '12px',
                    }}
                    formatter={(value: number) => [value, 'Count']}
                  />
                </PieChart>
              </ResponsiveContainer>
              <div className="flex-1 space-y-3">
                {exitReasonData.map((entry) => (
                  <div key={entry.name} className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <div 
                        className="w-3 h-3 rounded-full" 
                        style={{ backgroundColor: COLORS[entry.name as keyof typeof COLORS] || '#64748b' }}
                      />
                      <span className="text-sm text-slate-300">{entry.name}</span>
                    </div>
                    <span className="text-sm font-mono text-white">{entry.value}</span>
                  </div>
                ))}
              </div>
            </div>
          </motion.div>
        </div>

        {/* Trade History Table */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.5 }}
          className="bg-slate-800/40 backdrop-blur-xl rounded-2xl border border-white/10 overflow-hidden"
        >
          <div className="p-6 border-b border-white/10 flex items-center justify-between">
            <h3 className="font-bold text-white text-lg">Trade History</h3>
            <div className="text-sm text-slate-400">Click any trade to inspect details</div>
          </div>
          
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-white/10 bg-slate-900/30">
                  <th className="px-6 py-4 text-left text-xs font-medium text-slate-400 uppercase tracking-wider">ID</th>
                  <th className="px-6 py-4 text-left text-xs font-medium text-slate-400 uppercase tracking-wider">Entry Time</th>
                  <th className="px-6 py-4 text-left text-xs font-medium text-slate-400 uppercase tracking-wider">Symbol</th>
                  <th className="px-6 py-4 text-left text-xs font-medium text-slate-400 uppercase tracking-wider">Side</th>
                  <th className="px-6 py-4 text-right text-xs font-medium text-slate-400 uppercase tracking-wider">Entry $</th>
                  <th className="px-6 py-4 text-right text-xs font-medium text-slate-400 uppercase tracking-wider">Exit $</th>
                  <th className="px-6 py-4 text-right text-xs font-medium text-slate-400 uppercase tracking-wider">PnL</th>
                  <th className="px-6 py-4 text-left text-xs font-medium text-slate-400 uppercase tracking-wider">Exit Reason</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/5">
                {trades.map((trade, index) => (
                  <motion.tr
                    key={trade.id}
                    initial={{ opacity: 0, x: -20 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: 0.5 + index * 0.01 }}
                    onClick={() => onSelectTrade(trade)}
                    className="hover:bg-slate-700/30 cursor-pointer transition-colors group"
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
                    <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-white">
                      {trade.symbol}
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
  );
}