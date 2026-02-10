import React, { useMemo, useState, useEffect } from "react";
import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer, Legend } from "recharts";
import { useResultsStore } from "../../stores/resultsStore";
import { X } from "lucide-react";
import { cn } from "../../lib/utils";

const COLORS = {
  "TP1": "#22c55e", // Green
  "TP2": "#16a34a", // Darker Green
  "TP3": "#15803d", // Even Darker Green
  "LOCK_PROFIT": "#06b6d4", // Cyan
  "SL": "#ef4444", // Red
  "DISASTER_SL": "#7f1d1d", // Dark Red
  "MANUAL": "#a1a1aa" // Gray
};

export const ExitReasonsChart: React.FC = () => {
  const { exitReasons, setFilter, activeFilter } = useResultsStore();
  const [isMounted, setIsMounted] = useState(false);

  useEffect(() => {
    // Delay rendering of Recharts to ensure container has size
    // and to avoid the "width(-1)" error during initial layout
    const timer = setTimeout(() => setIsMounted(true), 100);
    return () => clearTimeout(timer);
  }, []);

  const data = useMemo(() => {
    return Object.entries(exitReasons).map(([name, value]) => ({ name, value }));
  }, [exitReasons]);

  const handleSliceClick = (entry: any) => {
      if (activeFilter === entry.name) {
          setFilter(null);
      } else {
          setFilter(entry.name);
      }
  };

  return (
    <div className="flex flex-col h-full">
        <div className="flex items-center justify-between mb-2">
            <h3 className="text-xs font-semibold text-text-secondary uppercase tracking-wider">Exit Reasons</h3>
            {activeFilter && (
                <button 
                    onClick={() => setFilter(null)}
                    className="flex items-center gap-1 px-2 py-0.5 rounded-full bg-accent-main/10 text-accent-main text-[10px] font-medium hover:bg-accent-main/20 transition-colors"
                >
                    <X size={10} />
                    Filter: {activeFilter}
                </button>
            )}
        </div>
        
        <div className="h-[180px] w-full relative">
            {isMounted && (
                <ResponsiveContainer width="100%" height="100%" minWidth={100} minHeight={100}>
                    <PieChart>
                        <Pie
                            data={data}
                            cx="50%"
                            cy="50%"
                            innerRadius={40}
                            outerRadius={70}
                            paddingAngle={2}
                            dataKey="value"
                            cursor="pointer"
                            onClick={handleSliceClick}
                        >
                            {data.map((entry, index) => (
                                <Cell 
                                    key={`cell-${index}`} 
                                    fill={COLORS[entry.name as keyof typeof COLORS] || "#888"} 
                                    stroke="transparent"
                                    className={cn(
                                        "transition-opacity duration-200",
                                        activeFilter && activeFilter !== entry.name ? "opacity-30" : "opacity-100 hover:opacity-80"
                                    )}
                                />
                            ))}
                        </Pie>
                        <Tooltip 
                            contentStyle={{ 
                                backgroundColor: 'var(--bg-elevated)', 
                                borderColor: 'var(--border-main)',
                                borderRadius: '0.5rem',
                                color: 'var(--text-primary)',
                                fontSize: '12px'
                            }}
                            itemStyle={{ color: 'var(--text-primary)' }}
                        />
                        <Legend 
                            layout="vertical" 
                            verticalAlign="middle" 
                            align="right"
                            wrapperStyle={{ fontSize: '10px', color: 'var(--text-secondary)' }}
                            iconSize={8}
                        />
                    </PieChart>
                </ResponsiveContainer>
            )}
            
            {/* Center Text (Total Trades) */}
            <div className="absolute inset-0 flex items-center justify-center pointer-events-none pr-14"> 
                <span className="text-xs font-mono text-text-muted opacity-50">
                    {Object.values(exitReasons).reduce((a, b) => a + b, 0)}
                </span>
            </div>
        </div>
    </div>
  );
};
