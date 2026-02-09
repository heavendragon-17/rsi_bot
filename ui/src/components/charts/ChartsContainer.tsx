import React from 'react';
import { EquityChart } from './EquityChart';
import { DrawdownChart } from './DrawdownChart';
import { TimeseriesData } from '../../types/pywebview';

interface ChartsContainerProps {
  data: TimeseriesData;
}

export const ChartsContainer: React.FC<ChartsContainerProps> = ({ data }) => {
  if (!data) return null;

  const equityData = data.equity_curve.map(([time, value]) => ({ time, value }));
  const drawdownData = data.drawdown_curve.map(([time, value]) => ({ time, value }));

  return (
    <div className="bg-surface border border-border rounded-xl p-4 shadow-sm space-y-4">
      <div>
        <h3 className="text-sm font-semibold text-text-muted mb-2">Equity Curve</h3>
        <EquityChart data={equityData} height={300} />
      </div>
      <div className="border-t border-border pt-4">
        <h3 className="text-sm font-semibold text-text-muted mb-2">Drawdown</h3>
        <DrawdownChart data={drawdownData} height={150} />
      </div>
    </div>
  );
};
