import { X, Code, TrendingUp, Calendar, DollarSign, Target } from 'lucide-react';
import { motion } from 'motion/react';
import { ComposedChart, Line, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine, Area } from 'recharts';

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

interface TradeDeepDiveProps {
  trade: Trade;
  onClose: () => void;
}

// Generate mock candlestick data
const generateCandleData = (entryPrice: number, exitPrice: number) => {
  const data = [];
  const numCandles = 100;
  let currentPrice = entryPrice * 0.97;
  
  for (let i = 0; i < numCandles; i++) {
    const volatility = 0.003;
    const change = (Math.random() - 0.5) * volatility * currentPrice;
    const open = currentPrice;
    const close = currentPrice + change;
    const high = Math.max(open, close) * (1 + Math.random() * volatility);
    const low = Math.min(open, close) * (1 - Math.random() * volatility);
    
    // Generate RSI data
    const rsi = 30 + Math.random() * 40;
    const wma45 = rsi + (Math.random() - 0.5) * 5;
    const ema9 = rsi + (Math.random() - 0.5) * 3;
    
    // Mark entry and exit points
    const isEntry = i === 20;
    const isExit = i === 75;
    
    if (isEntry) currentPrice = entryPrice;
    if (isExit) currentPrice = exitPrice;
    
    data.push({
      time: i,
      date: new Date(Date.now() - (numCandles - i) * 60 * 60 * 1000).toLocaleTimeString('en-US', { 
        hour: '2-digit', 
        minute: '2-digit' 
      }),
      open,
      high,
      low,
      close,
      price: close,
      rsi,
      wma45,
      ema9,
      volume: Math.random() * 1000 + 500,
      isEntry,
      isExit,
    });
    
    currentPrice = close;
  }
  
  return data;
};

export function TradeDeepDive({ trade, onClose }: TradeDeepDiveProps) {
  const chartData = generateCandleData(trade.entryPrice, trade.exitPrice);
  
  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-sm"
      onClick={onClose}
    >
      <motion.div
        initial={{ scale: 0.9, y: 20 }}
        animate={{ scale: 1, y: 0 }}
        exit={{ scale: 0.9, y: 20 }}
        onClick={(e) => e.stopPropagation()}
        className="w-full max-w-[1600px] max-h-[90vh] bg-slate-800/95 backdrop-blur-xl rounded-2xl border border-violet-500/30 shadow-[0_0_60px_rgba(139,92,246,0.3)] overflow-hidden flex flex-col"
      >
        {/* Header */}
        <div className="p-6 border-b border-white/10 bg-slate-900/50">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
              <div className={`p-3 rounded-xl ${trade.pnl > 0 ? 'bg-emerald-500/20' : 'bg-rose-500/20'}`}>
                <TrendingUp className={`w-6 h-6 ${trade.pnl > 0 ? 'text-emerald-400' : 'text-rose-400'}`} />
              </div>
              <div>
                <div className="flex items-center gap-3">
                  <h2 className="text-2xl font-bold text-white">Trade #{trade.id}</h2>
                  <span className={`
                    px-3 py-1 rounded-lg text-sm font-medium
                    ${trade.side === 'LONG' 
                      ? 'bg-emerald-500/20 text-emerald-400' 
                      : 'bg-rose-500/20 text-rose-400'}
                  `}>
                    {trade.side}
                  </span>
                  <span className="text-xl font-bold text-white">{trade.symbol}</span>
                </div>
                <div className={`text-lg font-mono mt-1 ${trade.pnl > 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                  {trade.pnl > 0 ? '+' : ''}${trade.pnl.toFixed(2)} ({trade.pnl > 0 ? '+' : ''}{trade.pnlPercent.toFixed(2)}%)
                </div>
              </div>
            </div>
            
            <div className="flex items-center gap-3">
              <button className="px-4 py-2 bg-violet-500/20 hover:bg-violet-500/30 text-violet-400 rounded-lg transition-colors flex items-center gap-2 border border-violet-500/30">
                <Code className="w-4 h-4" />
                Import Indicator Code
              </button>
              <button
                onClick={onClose}
                className="p-2 bg-slate-700/50 hover:bg-slate-700 text-slate-300 hover:text-white rounded-lg transition-all"
              >
                <X className="w-5 h-5" />
              </button>
            </div>
          </div>
        </div>

        {/* Trade Details Grid */}
        <div className="grid grid-cols-4 gap-4 p-6 bg-slate-900/30 border-b border-white/10">
          <div className="space-y-1">
            <div className="text-xs text-slate-400 flex items-center gap-2">
              <Calendar className="w-3 h-3" />
              Entry Time
            </div>
            <div className="text-sm text-white font-mono">
              {new Date(trade.entryTime).toLocaleString('en-US', {
                month: 'short',
                day: 'numeric',
                hour: '2-digit',
                minute: '2-digit'
              })}
            </div>
          </div>
          
          <div className="space-y-1">
            <div className="text-xs text-slate-400 flex items-center gap-2">
              <DollarSign className="w-3 h-3" />
              Entry Price
            </div>
            <div className="text-sm text-white font-mono">
              ${trade.entryPrice.toFixed(2)}
            </div>
          </div>
          
          <div className="space-y-1">
            <div className="text-xs text-slate-400 flex items-center gap-2">
              <DollarSign className="w-3 h-3" />
              Exit Price
            </div>
            <div className="text-sm text-white font-mono">
              ${trade.exitPrice.toFixed(2)}
            </div>
          </div>
          
          <div className="space-y-1">
            <div className="text-xs text-slate-400 flex items-center gap-2">
              <Target className="w-3 h-3" />
              Exit Reason
            </div>
            <div>
              <span className={`
                inline-flex px-2 py-1 rounded-md text-xs font-medium
                ${trade.exitReason === 'TP1' || trade.exitReason === 'TP2' 
                  ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30' 
                  : 'bg-rose-500/20 text-rose-400 border border-rose-500/30'}
              `}>
                {trade.exitReason}
              </span>
            </div>
          </div>
        </div>

        {/* Charts */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          {/* Price Chart */}
          <div className="bg-slate-900/50 rounded-xl p-6 border border-white/10">
            <div className="mb-4">
              <h3 className="text-white font-bold mb-1">Price Action</h3>
              <p className="text-xs text-slate-400">Candlestick chart with entry/exit markers</p>
            </div>
            <ResponsiveContainer width="100%" height={350}>
              <ComposedChart data={chartData}>
                <defs>
                  <linearGradient id="priceGradient" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#8B5CF6" stopOpacity={0.3} />
                    <stop offset="100%" stopColor="#8B5CF6" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#334155" opacity={0.3} />
                <XAxis 
                  dataKey="time" 
                  stroke="#64748b" 
                  tick={{ fill: '#94a3b8', fontSize: 11 }}
                  tickFormatter={(value) => {
                    if (value % 20 === 0) return chartData[value]?.date || '';
                    return '';
                  }}
                />
                <YAxis 
                  stroke="#64748b" 
                  tick={{ fill: '#94a3b8', fontSize: 11 }}
                  domain={['dataMin - 100', 'dataMax + 100']}
                  tickFormatter={(value) => `$${value.toFixed(0)}`}
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
                />
                
                {/* Entry Price Line */}
                <ReferenceLine 
                  y={trade.entryPrice} 
                  stroke="#8B5CF6" 
                  strokeDasharray="5 5" 
                  strokeWidth={2}
                  label={{ value: 'Entry', fill: '#8B5CF6', fontSize: 11, position: 'insideBottomRight' }}
                />
                
                {/* Exit Price Line */}
                <ReferenceLine 
                  y={trade.exitPrice} 
                  stroke="#06B6D4" 
                  strokeDasharray="5 5" 
                  strokeWidth={2}
                  label={{ value: 'Exit', fill: '#06B6D4', fontSize: 11, position: 'insideTopRight' }}
                />
                
                {/* Price Line */}
                <Area 
                  type="monotone" 
                  dataKey="price" 
                  stroke="#8B5CF6" 
                  strokeWidth={2}
                  fill="url(#priceGradient)"
                />
                
                {/* Entry/Exit Markers */}
                {chartData.filter(d => d.isEntry || d.isExit).map((point, i) => (
                  <ReferenceLine
                    key={i}
                    x={point.time}
                    stroke={point.isEntry ? '#10B981' : '#F43F5E'}
                    strokeWidth={2}
                    label={{
                      value: point.isEntry ? '▲' : '▼',
                      fill: point.isEntry ? '#10B981' : '#F43F5E',
                      fontSize: 16,
                      position: point.isEntry ? 'bottom' : 'top'
                    }}
                  />
                ))}
              </ComposedChart>
            </ResponsiveContainer>
          </div>

          {/* RSI Indicators */}
          <div className="bg-slate-900/50 rounded-xl p-6 border border-white/10">
            <div className="mb-4">
              <h3 className="text-white font-bold mb-1">RSI Indicators</h3>
              <p className="text-xs text-slate-400">RSI (14), WMA (45), EMA (9)</p>
            </div>
            <ResponsiveContainer width="100%" height={200}>
              <ComposedChart data={chartData}>
                <defs>
                  <linearGradient id="rsiGradient" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#06B6D4" stopOpacity={0.3} />
                    <stop offset="100%" stopColor="#06B6D4" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#334155" opacity={0.3} />
                <XAxis 
                  dataKey="time" 
                  stroke="#64748b" 
                  tick={{ fill: '#94a3b8', fontSize: 11 }}
                />
                <YAxis 
                  stroke="#64748b" 
                  tick={{ fill: '#94a3b8', fontSize: 11 }}
                  domain={[0, 100]}
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
                />
                
                {/* Overbought/Oversold zones */}
                <ReferenceLine y={70} stroke="#F43F5E" strokeDasharray="3 3" strokeOpacity={0.5} />
                <ReferenceLine y={30} stroke="#10B981" strokeDasharray="3 3" strokeOpacity={0.5} />
                
                <Area 
                  type="monotone" 
                  dataKey="rsi" 
                  stroke="#06B6D4" 
                  strokeWidth={2}
                  fill="url(#rsiGradient)"
                  name="RSI"
                />
                <Line 
                  type="monotone" 
                  dataKey="wma45" 
                  stroke="#8B5CF6" 
                  strokeWidth={2}
                  dot={false}
                  name="WMA45"
                />
                <Line 
                  type="monotone" 
                  dataKey="ema9" 
                  stroke="#34D399" 
                  strokeWidth={2}
                  dot={false}
                  name="EMA9"
                />
              </ComposedChart>
            </ResponsiveContainer>
          </div>

          {/* Volume */}
          <div className="bg-slate-900/50 rounded-xl p-6 border border-white/10">
            <div className="mb-4">
              <h3 className="text-white font-bold mb-1">Volume</h3>
              <p className="text-xs text-slate-400">Trading volume per period</p>
            </div>
            <ResponsiveContainer width="100%" height={150}>
              <ComposedChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#334155" opacity={0.3} />
                <XAxis 
                  dataKey="time" 
                  stroke="#64748b" 
                  tick={{ fill: '#94a3b8', fontSize: 11 }}
                />
                <YAxis 
                  stroke="#64748b" 
                  tick={{ fill: '#94a3b8', fontSize: 11 }}
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
                />
                <Bar 
                  dataKey="volume" 
                  fill="#475569"
                  radius={[4, 4, 0, 0]}
                />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        </div>
      </motion.div>
    </motion.div>
  );
}
