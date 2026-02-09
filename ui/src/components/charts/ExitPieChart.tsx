import React from 'react';
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip, Legend } from 'recharts';
import { useUIStore } from '../../stores/useUIStore';

interface ExitPieChartProps {
  data: Array<{ name: string; value: number }>;
}

export const ExitPieChart: React.FC<ExitPieChartProps> = ({ data }) => {
  const { theme } = useUIStore();
  const isDark = theme === 'dark' || theme === 'midnight';

  const COLORS = {
    tp: '#10b981', // Success
    sl: '#ef4444', // Danger
    signal: '#3b82f6', // Primary
    timeout: '#94a3b8' // Muted
  };

  return (
    <div className="w-full h-[300px]">
      <ResponsiveContainer width="100%" height="100%">
        <PieChart>
          <Pie
            data={data}
            cx="50%"
            cy="50%"
            innerRadius={60}
            outerRadius={80}
            paddingAngle={5}
            dataKey="value"
          >
            {data.map((entry, index) => (
              <Cell
                key={`cell-${index}`}
                fill={COLORS[entry.name as keyof typeof COLORS] || '#8884d8'}
                stroke={isDark ? '#1e293b' : '#ffffff'}
                strokeWidth={2}
              />
            ))}
          </Pie>
          <Tooltip
            contentStyle={{
              backgroundColor: isDark ? '#1e293b' : '#ffffff',
              borderColor: isDark ? '#334155' : '#cbd5e1',
              borderRadius: '8px',
              color: isDark ? '#f8fafc' : '#0f172a'
            }}
          />
          <Legend
            verticalAlign="bottom"
            height={36}
            formatter={(value) => <span className="text-text">{value.toUpperCase()}</span>}
          />
        </PieChart>
      </ResponsiveContainer>
    </div>
  );
};
