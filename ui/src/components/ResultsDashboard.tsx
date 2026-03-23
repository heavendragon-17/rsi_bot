// @ts-nocheck
import { useState, useEffect } from 'react';
import { LaunchpadConfig, StrategyConfig } from '../App';
import { TrendingUp, TrendingDown, Activity, Award, ChevronLeft, BarChart3, PieChart } from 'lucide-react';
import { motion, AnimatePresence } from 'motion/react';
import { TradeDeepDive } from './TradeDeepDive';
import { SinglePairResults } from './SinglePairResults';
import { BatchResults } from './BatchResults';

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

export interface SymbolPerformance {
  symbol: string;
  pnl: number;
  returnPercent: number;
  drawdown: number;
  winRate: number;
  totalTrades: number;
  wins: number;
  losses: number;
}

interface ResultsDashboardProps {
  strategyConfig: StrategyConfig;
  launchpadConfig: LaunchpadConfig;
  onBack: () => void;
}

// Mock data generator
const generateMockTrades = (symbol: string, count: number = 60): Trade[] => {
  const exitReasons = ['TP1', 'TP2', 'Stop Loss', 'Lock Profit', 'Time Exit'];
  const trades: Trade[] = [];

  for (let i = 0; i < count; i++) {
    const isWin = Math.random() > 0.32; // 68% win rate
    const entryPrice = 30000 + Math.random() * 10000;
    const pnlPercent = isWin
      ? 0.5 + Math.random() * 4
      : -(0.3 + Math.random() * 2);
    const exitPrice = entryPrice * (1 + pnlPercent / 100);

    trades.push({
      id: i + 1,
      entryTime: new Date(Date.now() - Math.random() * 30 * 24 * 60 * 60 * 1000).toISOString(),
      symbol,
      side: Math.random() > 0.5 ? 'LONG' : 'SHORT',
      entryPrice,
      exitPrice,
      pnl: (exitPrice - entryPrice) * (10 / entryPrice) * 10000,
      pnlPercent,
      exitReason: isWin ? exitReasons[Math.floor(Math.random() * 2)] : 'Stop Loss',
    });
  }

  return trades.sort((a, b) => new Date(b.entryTime).getTime() - new Date(a.entryTime).getTime());
};

const generateBatchPerformance = (): SymbolPerformance[] => {
  const symbols = [
    'DOGE/USDT', 'ORDI/USDT', 'BTC/USDT', 'ETH/USDT', 'SOL/USDT',
    'AVAX/USDT', 'MATIC/USDT', 'LINK/USDT', 'UNI/USDT', 'AAVE/USDT',
    'ATOM/USDT', 'DOT/USDT', 'ADA/USDT', 'XRP/USDT', 'LTC/USDT'
  ];

  return symbols.map(symbol => {
    const totalTrades = Math.floor(Math.random() * 30) + 20;
    const winRate = 0.5 + Math.random() * 0.35; // 50-85% win rate
    const wins = Math.floor(totalTrades * winRate);
    const losses = totalTrades - wins;
    const returnPercent = -5 + Math.random() * 25; // -5% to +20%
    const pnl = (returnPercent / 100) * 10000;
    const drawdown = Math.random() * 8;

    return {
      symbol,
      pnl,
      returnPercent,
      drawdown,
      winRate: winRate * 100,
      totalTrades,
      wins,
      losses,
    };
  }).sort((a, b) => b.returnPercent - a.returnPercent);
};

export function ResultsDashboard({ launchpadConfig, onBack }: ResultsDashboardProps) {
  const [selectedTrade, setSelectedTrade] = useState<Trade | null>(null);
  const isBatchMode = launchpadConfig.mode === 'batch';

  // Generate data based on mode
  const [singleTrades] = useState<Trade[]>(() =>
    isBatchMode ? [] : generateMockTrades(launchpadConfig.symbol || 'BTC/USDT', 60)
  );

  const [batchPerformance] = useState<SymbolPerformance[]>(() =>
    isBatchMode ? generateBatchPerformance() : []
  );

  const [selectedSymbol, setSelectedSymbol] = useState<string | null>(
    isBatchMode ? null : null
  );

  const [symbolTrades, setSymbolTrades] = useState<Trade[]>([]);

  // When a symbol is selected in batch mode, generate its trades
  useEffect(() => {
    if (selectedSymbol) {
      setSymbolTrades(generateMockTrades(selectedSymbol, 40));
    }
  }, [selectedSymbol]);

  return (
    <>
      {isBatchMode ? (
        <BatchResults
          batchPerformance={batchPerformance}
          selectedSymbol={selectedSymbol}
          onSelectSymbol={setSelectedSymbol}
          symbolTrades={symbolTrades}
          onSelectTrade={setSelectedTrade}
          onBack={onBack}
        />
      ) : (
        <SinglePairResults
          trades={singleTrades}
          symbol={launchpadConfig.symbol || 'BTC/USDT'}
          onSelectTrade={setSelectedTrade}
          onBack={onBack}
        />
      )}

      {/* Deep Dive Slide-over */}
      <AnimatePresence>
        {selectedTrade && (
          <TradeDeepDive trade={selectedTrade} onClose={() => setSelectedTrade(null)} />
        )}
      </AnimatePresence>
    </>
  );
}
