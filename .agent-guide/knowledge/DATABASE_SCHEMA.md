# Database Schema

> **For AI Agents** | SQLite table definitions

---

## 📍 Location

Database file: `data/backtest.db`

---

## 📊 Tables

### runs

Primary table for backtest run metadata.

```sql
CREATE TABLE runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    strategy_name TEXT NOT NULL,
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    start_date TEXT NOT NULL,
    end_date TEXT NOT NULL,
    created_at TEXT NOT NULL,
    config_json TEXT
);
```

---

### run_results

Performance metrics for each run.

```sql
CREATE TABLE run_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL,
    total_profit TEXT NOT NULL,  -- Decimal as TEXT
    win_rate REAL,
    total_trades INTEGER,
    profit_factor REAL,
    max_drawdown TEXT,
    sharpe_ratio REAL,
    metrics_json TEXT,  -- Additional metrics
    FOREIGN KEY (run_id) REFERENCES runs(id) ON DELETE CASCADE
);
```

---

### run_timeseries

Compressed equity and drawdown curves.

```sql
CREATE TABLE run_timeseries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL,
    equity_curve BLOB,      -- zlib compressed
    drawdown_curve BLOB,    -- zlib compressed
    FOREIGN KEY (run_id) REFERENCES runs(id) ON DELETE CASCADE
);
```

**Compression:**
```python
import zlib
import json

# Compress
data = [(1704067200, 10000), (1704153600, 10050), ...]
compressed = zlib.compress(json.dumps(data).encode())

# Decompress
data = json.loads(zlib.decompress(compressed).decode())
```

---

### trades

Individual trade records.

```sql
CREATE TABLE trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL,
    entry_time TEXT NOT NULL,
    exit_time TEXT,
    entry_price TEXT NOT NULL,   -- Decimal as TEXT
    exit_price TEXT,
    quantity TEXT NOT NULL,
    side TEXT NOT NULL,          -- 'long' or 'short'
    pnl TEXT,
    exit_reason TEXT,            -- 'tp', 'sl', 'signal', 'timeout'
    FOREIGN KEY (run_id) REFERENCES runs(id) ON DELETE CASCADE
);
```

---

### themes

UI theme definitions.

```sql
CREATE TABLE themes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    is_active INTEGER DEFAULT 0,  -- Boolean: 0 or 1
    colors_json TEXT NOT NULL
);
```

**Default themes to insert:**
```python
themes = [
    {
        "name": "dark",
        "is_active": 1,
        "colors_json": json.dumps({
            "bg": "#0f172a",
            "surface": "#1e293b",
            "text": "#f8fafc",
            "primary": "#3b82f6"
        })
    },
    {
        "name": "light",
        "is_active": 0,
        "colors_json": json.dumps({
            "bg": "#ffffff",
            "surface": "#f1f5f9",
            "text": "#0f172a",
            "primary": "#2563eb"
        })
    },
    {
        "name": "midnight",
        "is_active": 0,
        "colors_json": json.dumps({
            "bg": "#020617",
            "surface": "#0f172a",
            "text": "#e2e8f0",
            "primary": "#6366f1"
        })
    }
]
```

---

## 🔑 Important Rules

1. **Decimal precision:** Use `TEXT` for monetary values, `Decimal` in Python
2. **Lazy loading:** Only fetch `run_timeseries` when needed
3. **Cascade delete:** Deleting a run removes all related data
4. **Compress blobs:** Use zlib for timeseries data

---

## 📝 Example Queries

**Get run with results:**
```sql
SELECT r.*, rr.total_profit, rr.win_rate, rr.total_trades
FROM runs r
JOIN run_results rr ON r.id = rr.run_id
WHERE r.id = 1;
```

**Get trades for run:**
```sql
SELECT * FROM trades
WHERE run_id = 1
ORDER BY entry_time;
```

**Get active theme:**
```sql
SELECT * FROM themes WHERE is_active = 1;
```
