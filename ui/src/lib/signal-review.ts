export const REVIEW_CHART_CHUNK_CANDLES = 2_000;
export const REVIEW_SIGNAL_PAGE_SIZE = 50;
export const REVIEW_CHART_TIMEFRAMES = ["5m", "15m", "1h", "4h"] as const;

export type ReviewChartTimeframe = (typeof REVIEW_CHART_TIMEFRAMES)[number];

export const REVIEW_CHART_TIMEFRAME_MINUTES: Record<ReviewChartTimeframe, number> = {
  "5m": 5,
  "15m": 15,
  "1h": 60,
  "4h": 240,
};
