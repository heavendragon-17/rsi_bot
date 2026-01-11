## 2024-05-23 - [Resampling Optimization]
**Learning:** Resampling a large DataFrame (e.g., full history) is expensive O(N) and grows linearly with uptime. Most strategies only need the "head" (latest) of the resampled data for signal generation.
**Action:** Always slice the source DataFrame to the minimum required lookback (indicator warmup + buffer) *before* passing it to `resample_dataframe`. This caps the resampling cost to O(1) per tick, regardless of total accumulated history.
