import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer, Legend } from 'recharts';
import { useUIStore } from '../../stores/useUIStore';

interface ExitReason {
  name: string;
  value: number;
}

interface ExitPieChartProps {
  data: ExitReason[];
  height?: number;
}

const COLORS = ['#22c55e', '#ef4444', '#eab308', '#3b82f6', '#a855f7'];

export function ExitPieChart({ data, height = 300 }: ExitPieChartProps) {
  const { theme } = useUIStore();
  const isDark = theme?.is_dark ?? true;
  const textColor = isDark ? '#d1d5db' : '#374151';

  if (!data || data.length === 0) {
    return (
      <div className="flex items-center justify-center h-full text-[var(--color-text-muted)]">
        No exit data available
      </div>
    );
  }

  return (
    <div style={{ width: '100%', height }} className="border border-[var(--color-border)] rounded-lg p-2">
      <h3 className="text-sm font-semibold mb-2 text-[var(--color-text)]">Exit Reasons</h3>
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
            {data.map((_, index) => (
              <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
            ))}
          </Pie>
          <Tooltip 
            contentStyle={{ 
              backgroundColor: isDark ? '#1f2937' : '#ffffff',
              borderColor: isDark ? '#374151' : '#e5e7eb',
              color: textColor
            }}
          />
          <Legend />
        </PieChart>
      </ResponsiveContainer>
    </div>
  );
}
