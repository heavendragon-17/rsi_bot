import { useEffect, useRef } from 'react';
import { createChart, ColorType, IChartApi, HistogramSeries } from 'lightweight-charts';
import { useUIStore } from '../../stores/useUIStore';

interface DrawdownChartProps {
  data: Array<{ time: string; value: number }>; // Value should be negative percentage (e.g. -5.2)
  height?: number;
}

export function DrawdownChart({ data, height = 200 }: DrawdownChartProps) {
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
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

    const series = chart.addSeries(HistogramSeries, {
      color: '#ef4444', // Red-500
      priceFormat: {
        type: 'percent',
      },
    });

    const chartData = data.map(d => ({
      time: d.time.split('T')[0],
      value: d.value, // Expecting negative values
      color: '#ef4444',
    }));

    series.setData(chartData);
    chart.timeScale().fitContent();

    chartRef.current = chart;

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

  return (
    <div 
      ref={chartContainerRef} 
      className="w-full rounded-lg overflow-hidden border border-[var(--color-border)]"
    />
  );
}
