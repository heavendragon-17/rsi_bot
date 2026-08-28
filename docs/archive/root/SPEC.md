# Backtest Performance Optimization Spec

> **Historical implementation spec:** Retained for provenance; use
> `docs/11_testing_and_backtesting/` for the current backtest design.

## Hardware Context
- **CPU**: AMD Ryzen 7 7700 (8 cores / 16 threads)
- **GPU**: Intel Arc B780 (oneAPI/SYCL — not CUDA)

---

## Goals
- Maximize backtest speed across all modes
- Primary focus: **Portfolio mode** (currently the slowest)
- Secondary: Batch mode, Single mode
- GPU acceleration is a **stretch goal** — CPU-first

---

## Phase 1 — Critical Hot-Path Fixes (Do First)

### 1.1 Eliminate O(n²) DataFrame Slicing

**Problem**: `BacktestEventSource` passes `df.iloc[:i+1]` (a full growing copy) to `strategy.analyze()` on every bar. This is O(n²) total memory allocation and the single biggest bottleneck.

**Fix**: Pass `(full_df, current_index: int)` instead of a slice.
- Strategies replace `df.iloc[-1]` → `df.iloc[current_index]`
- Strategies replace `df.iloc[-2]` → `df.iloc[current_index - 1]`
- `.tail(lookback)` → `df.iloc[current_index - lookback + 1 : current_index + 1]`

**Interface change**: `IStrategy.analyze(df, current_index)` — **breaking change, intentional**.

**Scope**: Backtest-only fast path. Live mode (`MarketDataStore`) keeps the existing real-DataFrame interface unchanged. The backtest engine converts at the boundary before the event loop.

**Expected gain**: 3–6× on its own for large backtests.

---

### 1.2 Replace DataFrame with Pre-Extracted NumPy Arrays

**Problem**: Even with the slicing fix, pandas `.iloc` inside a hot loop has Python overhead per access.

**Fix**: At backtest start, extract all needed columns into contiguous NumPy arrays once:
```python
close  = df['close'].to_numpy()
high   = df['high'].to_numpy()
low    = df['low'].to_numpy()
open_  = df['open'].to_numpy()
# indicators
rsi    = df['rsi'].to_numpy()
# etc.
```
Strategy analyze functions receive these arrays + `current_index`. All indicator lookups become `rsi[i]`, `close[i-1]`, `close[i-lookback:i]` — zero pandas overhead.

**Expected gain**: Combined with 1.1, total **3–8× speedup** on the inner loop.

---

### 1.3 Selective Numba JIT on Numeric Inner Functions

Apply `@numba.njit` to the two most-called numeric functions:

| Function | Why JIT-friendly |
|---|---|
| Fill matching (order vs candle comparison) | Pure numeric comparisons, no Python objects |
| Per-candle equity calculation (sum unrealized PnL across positions) | Numeric reduction over positions array |

**Do NOT JIT**: Strategy logic (too complex, object-dependent), SQLite I/O, anything with dicts/strings.

**Numba vs Cython tradeoff**:
| | Numba | Cython |
|---|---|---|
| Setup | Zero (decorators only) | Build step required |
| Speedup on numeric loops | 5–50× | 5–30× |
| Flexibility | Limited types | Full C control |
| Maintenance | Easy | Harder |

→ **Use Numba**. It fits the target functions perfectly and requires no build infrastructure.

**Expected gain**: Additional **2–5×** on fill matching + equity calc on top of Phase 1.1/1.2.

**Combined Phase 1 estimate**: **10–20× total** speedup.

---

## Phase 2 — Portfolio Mode: Timestamp-Aligned Batch Processing

### 2.1 Replace Heap-Based Event Loop with Vectorized Batch Loop

**Current**: Single-threaded heap pops one `(timestamp, symbol)` event at a time → sequential, no vectorization possible.

**New**: Pre-sort all symbols into a time-aligned matrix. For each unique timestamp, process ALL symbols with a candle at that time as a batch using vectorized NumPy ops.

```
timestamps × symbols matrix (shape: T × S)
Each row = one timestamp, process entire row at once
```

**Padding/masking**: Symbols without a candle at timestamp `t` get `NaN` values and a boolean mask. All vectorized ops use `np.nansum`, masked arrays, or `mask * value` patterns.

**Liquidation**: Within-timestamp ordering is lost (all symbols at `t` processed together). This is acceptable — same-timestamp sequencing is arbitrary in a backtest. Liquidation checks happen per-timestamp-batch.

**Expected gain**: Eliminates Python loop overhead across symbols — scales with symbol count. For 18 symbols this is significant; for 100+ symbols it's transformative.

---

### 2.2 Adaptive Equity Curve Sampling

**Problem**: Equity curve records one point per candle (all symbols, every bar). For 18 symbols × 5 months × 5m candles ≈ 780K equity points, each requiring iteration over all open positions.

**Fix**: Adaptive sampling strategy:
- Default: sample every **15 minutes** (3 candles on 5m TF)
- When drawdown is steep (equity drop > threshold vs previous sample): switch to **every-candle** resolution for that window
- When flat/steady: can stretch to every 30 min

Threshold for high-resolution switch: configurable, default `2%` drawdown in the sampling window.

This preserves granularity where it matters (for the drawdown curve in UI) while cutting equity recording cost by ~3× on average.

---

### 2.3 Concurrent Portfolio Runs (Parameter Sweeps)

**For parameter optimization sweeps** (many independent portfolio runs):
- Use `ProcessPoolExecutor(max_workers=N)` where N = CPU core count (default 8 for Ryzen 7 7700)
- Each process runs a fully independent portfolio backtest
- No shared state between processes

**For single runs with many symbols** (primary focus):
- This is handled by Phase 2.1 (vectorized batch loop)
- Single-run parallelism is limited by the sequential event loop — vectorization is the right tool here, not multiprocessing

---

## Phase 3 — GPU Acceleration (Stretch Goal)

### Why it's high-risk / deferred

Intel Arc B780 uses **oneAPI/SYCL**, not CUDA. This means:
- **Numba CUDA**: ❌ not compatible
- **CuPy**: ❌ not compatible
- **Intel dpnp** (NumPy on GPU via SYCL): ✅ available but less mature
- **numba-dpex** (SYCL JIT): ✅ experimental, limited op coverage

GPU helps backtesting in two scenarios:
1. **Vectorized indicator computation** — already done once via `pandas_ta` before the loop; not the bottleneck
2. **Thousands of parameter combos in parallel** — requires rewriting core loop for GPU execution

The ROI is high-risk because: the core bottleneck is Python interpreter overhead + memory allocation (CPU-side), not floating-point throughput. GPU can't help with Python overhead. Rewriting the loop in SYCL/dpnp is a major engineering effort with uncertain payoff given the library maturity.

**Decision**: Implement Phase 1 + 2 first. If runtime is still unsatisfactory after 10–20× CPU gains, revisit GPU for parameter sweep parallelism only (not single-run speedup).

---

## Correctness Verification

After each optimization phase, run a **full regression suite**:
- Run identical backtest (same symbol set, date range, strategy config) before and after each change
- Compare trade-by-trade: entry timestamp, exit timestamp, PnL — must match within tolerance (`1e-8` for floats)
- Compare final equity, max drawdown, Sharpe ratio
- Flag any divergence as a blocker before merging

---

## Implementation Order

| Priority | Change | Estimated Gain | Risk |
|---|---|---|---|
| 1 | Eliminate `df.iloc[:i+1]` slicing (1.1) | 3–6× | Low (interface change scoped to backtest) |
| 2 | NumPy array extraction (1.2) | +2–3× combined | Low |
| 3 | Numba JIT on fill + equity calc (1.3) | +2–5× | Low-Medium |
| 4 | Timestamp-aligned batch loop (2.1) | Significant for many symbols | Medium |
| 5 | Adaptive equity sampling (2.2) | 2–3× on equity recording | Low |
| 6 | ProcessPoolExecutor for sweeps (2.3) | Linear with core count | Low |
| 7 | GPU (dpnp/numba-dpex) | Unknown | High |

---

## Out of Scope
- Changing indicator computation (already vectorized via `pandas_ta`)
- Live trading mode changes (backtest-only fast path)
- Database schema changes beyond what's needed for compressed equity curves
