import React, { useEffect, useRef } from 'react';
import { createChart, ColorType, IChartApi, LineSeries } from 'lightweight-charts';
import { useUIStore } from '../../stores/useUIStore';

interface EquityChartProps {
  data: Array<{ time: number; value: number }>;
  height?: number;
}

export const EquityChart: React.FC<EquityChartProps> = ({ data, height = 300 }) => {
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const { theme } = useUIStore();

  useEffect(() => {
    if (!chartContainerRef.current) return;

    const isDark = theme === 'dark' || theme === 'midnight';
    const textColor = isDark ? '#f8fafc' : '#0f172a';
    const lineColor = isDark ? '#334155' : '#cbd5e1';

    const chart = createChart(chartContainerRef.current, {
      width: chartContainerRef.current.clientWidth,
      height: height,
      layout: {
        background: { type: ColorType.Solid, color: 'transparent' },
        textColor: textColor,
      },
      grid: {
        vertLines: { color: lineColor },
        horzLines: { color: lineColor },
      },
      timeScale: {
        timeVisible: true,
        secondsVisible: false,
      },
    });

    const series = chart.addSeries(LineSeries, {
      color: '#3b82f6',
      lineWidth: 2,
    });

    const chartData = data.map(d => ({
      time: d.time as any,
      value: d.value
    }));

    series.setData(chartData);
    chart.timeScale().fitContent();

    chartRef.current = chart;

    const handleResize = () => {
      if (chartContainerRef.current) {
        chart.applyOptions({ width: chartContainerRef.current.clientWidth });
      }
    };

    window.addEventListener('resize', handleResize);

    return () => {
      window.removeEventListener('resize', handleResize);
      chart.remove();
    };
  }, [data, height, theme]);

  return <div ref={chartContainerRef} className="w-full" />;
};
