# Database Schema: Backtest UI (CTO-Approved)

> SQLite database optimized for **data integrity** and **UI performance**.

---

## Design Principles

| Principle           | Implementation                                                  |
| ------------------- | --------------------------------------------------------------- |
| **Money Precision** | Use `TEXT` for all monetary values, parse with Python `Decimal` |
| **UI Performance**  | Heavy blobs (equity_curve) in separate table for lazy loading   |
| **Reproducibility** | Store `git_hash` and `version` to trace code changes            |
| **Audit Trail**     | Explicit `fee_tier` and `slippage_model` columns                |

---

## File Location

```
rsi_bot/data/backtest.db
```

---

## Tables Overview

| Table            | Purpose                                | Load Pattern   |
| ---------------- | -------------------------------------- | -------------- |
| `strategies`     | Available strategies + default configs | Always         |
| `runs`           | Individual backtest runs               | Always         |
| `run_configs`    | Configuration used for each run        | Always         |
| `run_results`    | Scalar performance metrics (fast)      | Dashboard list |
| `run_timeseries` | Heavy time-series (lazy load)          | On-click only  |
| `trades`         | Individual trades                      | On-click only  |
| `tags`           | Labels for runs                        | Always         |
| `comparisons`    | Saved run comparisons                  | On-click only  |
| `themes`         | UI themes (scalable)                   | Always         |

---

## Full Schema

```sql
-- ============================================
-- STRATEGIES TABLE
-- ============================================
CREATE TABLE strategies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    description TEXT,
    default_config JSON NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Seed data
INSERT INTO strategies (name, description, default_config) VALUES
('rsi_no_retest', 'RSI strategy without retest confirmation', '{
    "rsi_period": 21,
    "rsi_ema_length": 9,
    "rsi_wma_length": 45,
    "price_ema_fast": 21,
    "price_ema_slow": 200,
    "nr_lookback": 30,
    "nr_max_above_ema21": 1,
    "nr_rsi_spread_min": 1.5,
    "nr_sl_mode": "lowest_close",
    "sl_buffer_pct": 0.0,
    "disaster_sl_multiplier": 3.0,
    "nr_tp1_rr": 1.0,
    "nr_tp2_rr": 2.0,
    "nr_tp3_rr": 3.0,
    "tp1_close_pct": 0.50,
    "tp2_close_pct": 0.50,
    "nr_move_sl_rr": 0.5,
    "nr_lock_profit_rr": 0.2
}');

-- ============================================
-- THEMES TABLE (Scalable for N themes)
-- ============================================
CREATE TABLE themes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,         -- "cyberpunk_neon", "beach_paradise"
    display_name TEXT NOT NULL,        -- "Cyberpunk Neon", "Beach Paradise"
    is_dark BOOLEAN DEFAULT TRUE,
    css_variables JSON NOT NULL,       -- All CSS custom properties
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Seed themes
INSERT INTO themes (name, display_name, is_dark, css_variables) VALUES
('cyberpunk_neon', 'Cyberpunk Neon', TRUE, '{
    "--bg-primary": "#0F172A",
    "--bg-secondary": "#1E293B",
    "--bg-surface": "rgba(30, 41, 59, 0.4)",
    "--text-primary": "#F8FAFC",
    "--text-secondary": "#94A3B8",
    "--text-muted": "#64748B",
    "--accent": "#8B5CF6",
    "--accent-hover": "#7C3AED",
    "--success": "#10B981",
    "--success-light": "#34D399",
    "--danger": "#F43F5E",
    "--danger-light": "#FB7185",
    "--border": "rgba(255, 255, 255, 0.1)",
    "--glow": "rgba(139, 92, 246, 0.3)"
}'),
('beach_paradise', 'Beach Paradise', FALSE, '{
    "--bg-primary": "#FEF3E2",
    "--bg-secondary": "#FDE8CD",
    "--bg-surface": "rgba(255, 255, 255, 0.8)",
    "--text-primary": "#1E293B",
    "--text-secondary": "#475569",
    "--text-muted": "#64748B",
    "--accent": "#0D9488",
    "--accent-hover": "#0F766E",
    "--success": "#059669",
    "--success-light": "#34D399",
    "--danger": "#DC2626",
    "--danger-light": "#F87171",
    "--border": "rgba(0, 0, 0, 0.1)",
    "--glow": "rgba(13, 148, 136, 0.2)"
}'),
('midnight_ocean', 'Midnight Ocean', TRUE, '{
    "--bg-primary": "#0A1628",
    "--bg-secondary": "#132337",
    "--bg-surface": "rgba(19, 35, 55, 0.6)",
    "--text-primary": "#E2E8F0",
    "--text-secondary": "#94A3B8",
    "--text-muted": "#64748B",
    "--accent": "#0EA5E9",
    "--accent-hover": "#0284C7",
    "--success": "#22C55E",
    "--success-light": "#4ADE80",
    "--danger": "#EF4444",
    "--danger-light": "#F87171",
    "--border": "rgba(255, 255, 255, 0.08)",
    "--glow": "rgba(14, 165, 233, 0.25)"
}');

-- ============================================
-- RUNS TABLE (with Version Control)
-- ============================================
CREATE TABLE runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    strategy_id INTEGER NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    started_at DATETIME,
    completed_at DATETIME,
    status TEXT DEFAULT 'pending', -- pending, running, completed, failed

    -- VERSION CONTROL (CTO Requirement)
    git_hash TEXT,    -- Commit hash when test ran, e.g., "a1b2c3d"
    version TEXT,     -- Semantic version, e.g., "v1.0.2"

    -- Grid search support
    is_grid_search BOOLEAN DEFAULT FALSE,
    grid_search_parent_id INTEGER,
    grid_search_total INTEGER,
    grid_search_completed INTEGER,

    FOREIGN KEY (strategy_id) REFERENCES strategies(id),
    FOREIGN KEY (grid_search_parent_id) REFERENCES runs(id)
);

-- ============================================
-- RUN CONFIGS TABLE (with Simulation Costs)
-- ============================================
CREATE TABLE run_configs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL UNIQUE,

    -- Symbols
    symbol TEXT NOT NULL,
    symbols_list JSON,
    is_batch_mode BOOLEAN DEFAULT FALSE,

    -- Timeframe
    timeframe TEXT NOT NULL,

    -- Date range
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    lookback_value INTEGER,
    lookback_unit TEXT,

    -- Capital & Risk (TEXT for precision)
    initial_capital TEXT DEFAULT '10000.00',
    leverage INTEGER DEFAULT 10,
    risk_per_trade_pct TEXT DEFAULT '0.02',

    -- SIMULATION COSTS (CTO Requirement)
    fee_tier TEXT DEFAULT '0.001',       -- 0.1% = Binance VIP0
    slippage_model TEXT DEFAULT 'none',  -- "none", "fixed_pct", "variable"
    slippage_pct TEXT DEFAULT '0.0',     -- Only if slippage_model != "none"

    -- Strategy parameters
    params JSON NOT NULL,

    FOREIGN KEY (run_id) REFERENCES runs(id)
);

-- ============================================
-- RUN RESULTS TABLE (Optimized for Fast Reads)
-- ============================================
CREATE TABLE run_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL UNIQUE,

    -- Use TEXT for precise decimals (CTO Requirement)
    net_profit TEXT,
    net_profit_pct REAL,
    gross_profit TEXT,
    gross_loss TEXT,

    -- Performance (REAL is fine for ratios/percentages)
    win_rate REAL,
    profit_factor REAL,
    expectancy TEXT,

    -- Risk metrics
    max_drawdown_pct REAL,
    max_drawdown_value TEXT,
    max_drawdown_duration_days REAL,
    volatility REAL,

    -- Ratios
    sharpe_ratio REAL,
    sortino_ratio REAL,
    calmar_ratio REAL,

    -- Trade stats
    total_trades INTEGER,
    winning_trades INTEGER,
    losing_trades INTEGER,
    avg_win TEXT,
    avg_loss TEXT,
    largest_win TEXT,
    largest_loss TEXT,
    max_consecutive_wins INTEGER,
    max_consecutive_losses INTEGER,
    avg_hold_time_hours REAL,

    -- Exit reason summary (small JSON, OK to keep here)
    exit_reasons JSON,

    -- REMOVED: equity_curve, monthly_returns (moved to run_timeseries)

    FOREIGN KEY (run_id) REFERENCES runs(id)
);

-- ============================================
-- RUN TIMESERIES TABLE (Lazy Loading - CTO Requirement)
-- ============================================
CREATE TABLE run_timeseries (
    run_id INTEGER PRIMARY KEY,

    -- Heavy time-series data (only fetched on click)
    equity_curve BLOB,     -- Compressed JSON: [{"date": "...", "balance": "..."}, ...]
    drawdown_curve BLOB,   -- Compressed JSON: [{"date": "...", "drawdown": ...}, ...]
    monthly_returns JSON,  -- {"2025-01": 5.2, "2025-02": -1.3, ...}

    FOREIGN KEY (run_id) REFERENCES runs(id)
);

-- ============================================
-- TRADES TABLE (with Precise Decimals)
-- ============================================
CREATE TABLE trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL,

    -- Trade identification
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,

    -- Timing
    entry_time DATETIME NOT NULL,
    exit_time DATETIME,
    hold_time_hours REAL,

    -- Prices (TEXT for precision)
    entry_price TEXT NOT NULL,
    exit_price TEXT,
    stop_loss_price TEXT,
    tp1_price TEXT,
    tp2_price TEXT,
    tp3_price TEXT,

    -- Size (TEXT for precision)
    quantity TEXT NOT NULL,
    size_usd TEXT NOT NULL,

    -- Results (TEXT for precision)
    pnl TEXT,
    pnl_pct REAL,
    exit_reason TEXT,

    -- User annotations
    note TEXT,

    -- REMOVED: chart_data (too heavy, fetch from candle API if needed)

    FOREIGN KEY (run_id) REFERENCES runs(id)
);

-- ============================================
-- TAGS TABLE
-- ============================================
CREATE TABLE tags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    color TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (run_id) REFERENCES runs(id),
    UNIQUE(run_id, name)
);

-- ============================================
-- COMPARISONS TABLE
-- ============================================
CREATE TABLE comparisons (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    run_a_id INTEGER NOT NULL,
    run_b_id INTEGER NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    notes TEXT,
    diff_summary JSON,

    FOREIGN KEY (run_a_id) REFERENCES runs(id),
    FOREIGN KEY (run_b_id) REFERENCES runs(id)
);

-- ============================================
-- INDEXES
-- ============================================
CREATE INDEX idx_runs_strategy ON runs(strategy_id);
CREATE INDEX idx_runs_created ON runs(created_at DESC);
CREATE INDEX idx_runs_status ON runs(status);
CREATE INDEX idx_runs_grid_parent ON runs(grid_search_parent_id);
CREATE INDEX idx_run_configs_symbol ON run_configs(symbol);
CREATE INDEX idx_trades_run ON trades(run_id);
CREATE INDEX idx_trades_symbol ON trades(symbol);
CREATE INDEX idx_tags_run ON tags(run_id);
CREATE INDEX idx_tags_name ON tags(name);
CREATE INDEX idx_themes_name ON themes(name);
```

---

## Query Patterns (CTO-Approved)

### Dashboard List (Fast - No Blobs)

```sql
SELECT r.id, s.name, rr.net_profit_pct, rr.sharpe_ratio, rr.win_rate
FROM runs r
JOIN run_results rr ON r.id = rr.run_id
JOIN strategies s ON r.strategy_id = s.id
WHERE r.status = 'completed'
ORDER BY r.created_at DESC
LIMIT 50;
```

### Detailed Chart (On Click - Lazy Load)

```sql
SELECT equity_curve, drawdown_curve, monthly_returns
FROM run_timeseries
WHERE run_id = ?;
```

### Get Active Theme

```sql
SELECT css_variables FROM themes WHERE name = ?;
```

### Add New Theme (Scalable)

```sql
INSERT INTO themes (name, display_name, is_dark, css_variables)
VALUES ('forest_green', 'Forest Green', TRUE, '{"--bg-primary": "#0B1D0B", ...}');
```

---

## Python Decimal Handling

```python
from decimal import Decimal

# When inserting
def insert_trade(cursor, trade):
    cursor.execute("""
        INSERT INTO trades (entry_price, pnl, size_usd, ...)
        VALUES (?, ?, ?, ...)
    """, (
        str(trade.entry_price),  # Decimal → TEXT
        str(trade.pnl),
        str(trade.size_usd),
        ...
    ))

# When reading
def get_trade(cursor, trade_id):
    row = cursor.fetchone()
    return {
        'entry_price': Decimal(row['entry_price']),  # TEXT → Decimal
        'pnl': Decimal(row['pnl']),
        ...
    }
```

---

## BLOB Compression (CTO Requirement)

> ⚠️ **CRITICAL**: The `equity_curve` and `drawdown_curve` columns are `BLOB`, not `JSON`.
> You **MUST** compress data before storing and decompress when reading.

```python
import zlib
import json

def save_timeseries(cursor, run_id, equity_list, drawdown_list=None):
    """Save compressed time-series data to run_timeseries table."""
    # 1. Convert to JSON string
    equity_json = json.dumps(equity_list)

    # 2. Compress to bytes (zlib is fast and standard)
    equity_compressed = zlib.compress(equity_json.encode('utf-8'))

    # 3. Optional: compress drawdown if provided
    drawdown_compressed = None
    if drawdown_list:
        drawdown_json = json.dumps(drawdown_list)
        drawdown_compressed = zlib.compress(drawdown_json.encode('utf-8'))

    # 4. Insert BLOB
    cursor.execute("""
        INSERT INTO run_timeseries (run_id, equity_curve, drawdown_curve)
        VALUES (?, ?, ?)
    """, (run_id, equity_compressed, drawdown_compressed))


def load_timeseries(cursor, run_id):
    """Load and decompress time-series data from run_timeseries table."""
    cursor.execute("""
        SELECT equity_curve, drawdown_curve, monthly_returns
        FROM run_timeseries
        WHERE run_id = ?
    """, (run_id,))
    row = cursor.fetchone()

    if not row:
        return {'equity_curve': [], 'drawdown_curve': [], 'monthly_returns': {}}

    result = {}

    # Decompress equity_curve
    if row[0]:
        json_str = zlib.decompress(row[0]).decode('utf-8')
        result['equity_curve'] = json.loads(json_str)
    else:
        result['equity_curve'] = []

    # Decompress drawdown_curve
    if row[1]:
        json_str = zlib.decompress(row[1]).decode('utf-8')
        result['drawdown_curve'] = json.loads(json_str)
    else:
        result['drawdown_curve'] = []

    # monthly_returns is regular JSON (not compressed, it's small)
    result['monthly_returns'] = json.loads(row[2]) if row[2] else {}

    return result


# Compression ratio example:
# 2-year equity curve (1-min data) = ~1M data points
# Uncompressed JSON: ~25 MB
# Compressed BLOB:   ~2-3 MB (90% reduction)
```

---

## Migration Commands

```bash
# Initialize database
python cli/db_manager.py init

# Run migrations (if schema changes)
python cli/db_manager.py migrate

# Seed default strategies and themes
python cli/db_manager.py seed
```
