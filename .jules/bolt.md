## 2024-05-23 - [Resampling Optimization]
**Learning:** Resampling a growing DataFrame (e.g., inside a backtest loop) is an O(N^2) operation over the course of the backtest if the entire history is passed each time.
**Action:** When resampling for higher timeframe indicators (e.g., H1 checks on 5m data), always slice the input DataFrame to the minimum required history (e.g., ~166 hours or 10,000 1m candles) to ensure O(1) resampling cost per iteration.
