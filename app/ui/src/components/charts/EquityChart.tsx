import { useEffect, useRef } from 'react';
import { createChart, ColorType, IChartApi, ISeriesApi, AreaSeries } from 'lightweight-charts';
import { useUIStore } from '../../stores/useUIStore';

interface EquityChartProps {
  data: Array<{ time: string; value: number }>;
  height?: number;
}

export function EquityChart({ data, height = 400 }: EquityChartProps) {
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Area"> | null>(null);
  const { theme } = useUIStore();

  const isDark = theme?.is_dark ?? true;
  const backgroundColor = isDark ? '#1a1b1e' : '#ffffff';
  const textColor = isDark ? '#d1d5db' : '#374151';
  const gridColor = isDark ? '#2c2e33' : '#e5e7eb';

  useEffect(() => {
    if (!chartContainerRef.current) return;

    const chart = createChart(chartContainerRef.current, {
      width: chartContainerRef.current.clientWidth,
      height: height,
      layout: {
        background: { type: ColorType.Solid, color: backgroundColor },
        textColor: textColor,
      },
      grid: {
        vertLines: { color: gridColor },
        horzLines: { color: gridColor },
      },
      rightPriceScale: {
        borderColor: gridColor,
      },
      timeScale: {
        borderColor: gridColor,
        timeVisible: true,
      },
    });

    const series = chart.addSeries(AreaSeries, {
      lineColor: '#2563eb', // Blue-600
      topColor: 'rgba(37, 99, 235, 0.4)',
      bottomColor: 'rgba(37, 99, 235, 0.0)',
      lineWidth: 2,
    });

    // Format data for lightweight-charts
    // Ensure data is sorted by time and time is string 'YYYY-MM-DD' or timestamp
    const chartData = data.map(d => ({
      time: d.time.split('T')[0], // Simple date string for now
      value: d.value,
    }));

    series.setData(chartData);
    chart.timeScale().fitContent();

    chartRef.current = chart;
    seriesRef.current = series;

    const handleResize = () => {
      if (chartContainerRef.current && chartRef.current) {
        chartRef.current.applyOptions({ 
          width: chartContainerRef.current.clientWidth 
        });
      }
    };

    window.addEventListener('resize', handleResize);

    return () => {
      window.removeEventListener('resize', handleResize);
      chart.remove();
    };
  }, [data, height, backgroundColor, textColor, gridColor]);

  // Update data without destroying chart
  useEffect(() => {
    if (seriesRef.current && data.length > 0) {
      const chartData = data.map(d => ({
        time: d.time.split('T')[0],
        value: d.value,
      }));
      seriesRef.current.setData(chartData);
      chartRef.current?.timeScale().fitContent();
    }
  }, [data]);

  return (
    <div 
      ref={chartContainerRef} 
      className="w-full rounded-lg overflow-hidden border border-[var(--color-border)]"
    />
  );
}
