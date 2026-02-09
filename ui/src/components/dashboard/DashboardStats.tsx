import React from 'react';
import { TrendingUp, Target, Activity, BarChart2 } from 'lucide-react';
import { cn } from '../../lib/utils';

interface StatCardProps {
  label: string;
  value: string | number;
  icon: React.ElementType;
  trend?: string;
  color?: string;
}

const StatCard: React.FC<StatCardProps> = ({ label, value, icon: Icon, color = "text-primary" }) => (
  <div className="bg-surface border border-border rounded-xl p-5 flex items-start justify-between shadow-sm">
    <div>
      <p className="text-text-muted text-sm font-medium mb-1">{label}</p>
      <h3 className="text-2xl font-bold text-text">{value}</h3>
    </div>
    <div className={cn("p-3 rounded-lg bg-surface-hover", color)}>
      <Icon size={24} />
    </div>
  </div>
);

interface DashboardStatsProps {
  stats?: {
    totalProfit: number;
    winRate: number;
    totalTrades: number;
    profitFactor: number;
  };
}

export const DashboardStats: React.FC<DashboardStatsProps> = ({ stats }) => {
  // Use provided stats or defaults
  const data = stats || {
    totalProfit: 0,
    winRate: 0,
    totalTrades: 0,
    profitFactor: 0
  };

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
      <StatCard
        label="Total Profit"
        value={`$${data.totalProfit.toLocaleString()}`}
        icon={TrendingUp}
        color="text-success"
      />
      <StatCard
        label="Win Rate"
        value={`${(data.winRate * 100).toFixed(1)}%`}
        icon={Target}
        color="text-info"
      />
      <StatCard
        label="Total Trades"
        value={data.totalTrades}
        icon={Activity}
        color="text-warning"
      />
      <StatCard
        label="Profit Factor"
        value={data.profitFactor.toFixed(2)}
        icon={BarChart2}
        color="text-primary"
      />
    </div>
  );
};
