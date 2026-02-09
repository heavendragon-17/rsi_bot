import sqlite3
from pathlib import Path
from app.db.connection import DB_PATH

SCHEMA = """
-- ============================================
-- STRATEGIES TABLE
-- ============================================
CREATE TABLE IF NOT EXISTS strategies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    description TEXT,
    default_config JSON NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Seed data
INSERT OR IGNORE INTO strategies (name, description, default_config) VALUES
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
-- THEMES TABLE
-- ============================================
CREATE TABLE IF NOT EXISTS themes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    is_dark BOOLEAN DEFAULT TRUE,
    css_variables JSON NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Seed themes
INSERT OR IGNORE INTO themes (name, display_name, is_dark, css_variables) VALUES
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
-- RUNS TABLE
-- ============================================
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    strategy_id INTEGER NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    started_at DATETIME,
    completed_at DATETIME,
    status TEXT DEFAULT 'pending',
    git_hash TEXT,
    version TEXT,
    is_grid_search BOOLEAN DEFAULT FALSE,
    grid_search_parent_id INTEGER,
    grid_search_total INTEGER,
    grid_search_completed INTEGER,
    FOREIGN KEY (strategy_id) REFERENCES strategies(id),
    FOREIGN KEY (grid_search_parent_id) REFERENCES runs(id)
);

-- ============================================
-- RUN CONFIGS TABLE
-- ============================================
CREATE TABLE IF NOT EXISTS run_configs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL UNIQUE,
    symbol TEXT NOT NULL,
    symbols_list JSON,
    is_batch_mode BOOLEAN DEFAULT FALSE,
    timeframe TEXT NOT NULL,
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    lookback_value INTEGER,
    lookback_unit TEXT,
    initial_capital TEXT DEFAULT '10000.00',
    leverage INTEGER DEFAULT 10,
    risk_per_trade_pct TEXT DEFAULT '0.02',
    fee_tier TEXT DEFAULT '0.001',
    slippage_model TEXT DEFAULT 'none',
    slippage_pct TEXT DEFAULT '0.0',
    params JSON NOT NULL,
    FOREIGN KEY (run_id) REFERENCES runs(id)
);

-- ============================================
-- RUN RESULTS TABLE
-- ============================================
CREATE TABLE IF NOT EXISTS run_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL UNIQUE,
    net_profit TEXT,
    net_profit_pct REAL,
    gross_profit TEXT,
    gross_loss TEXT,
    win_rate REAL,
    profit_factor REAL,
    expectancy TEXT,
    max_drawdown_pct REAL,
    max_drawdown_value TEXT,
    max_drawdown_duration_days REAL,
    volatility REAL,
    sharpe_ratio REAL,
    sortino_ratio REAL,
    calmar_ratio REAL,
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
    exit_reasons JSON,
    FOREIGN KEY (run_id) REFERENCES runs(id)
);

-- ============================================
-- RUN TIMESERIES TABLE
-- ============================================
CREATE TABLE IF NOT EXISTS run_timeseries (
    run_id INTEGER PRIMARY KEY,
    equity_curve BLOB,
    drawdown_curve BLOB,
    monthly_returns JSON,
    FOREIGN KEY (run_id) REFERENCES runs(id)
);

-- ============================================
-- TRADES TABLE
-- ============================================
CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    entry_time DATETIME NOT NULL,
    exit_time DATETIME,
    hold_time_hours REAL,
    entry_price TEXT NOT NULL,
    exit_price TEXT,
    stop_loss_price TEXT,
    tp1_price TEXT,
    tp2_price TEXT,
    tp3_price TEXT,
    quantity TEXT NOT NULL,
    size_usd TEXT NOT NULL,
    pnl TEXT,
    pnl_pct REAL,
    exit_reason TEXT,
    note TEXT,
    FOREIGN KEY (run_id) REFERENCES runs(id)
);

-- ============================================
-- TAGS TABLE
-- ============================================
CREATE TABLE IF NOT EXISTS tags (
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
CREATE TABLE IF NOT EXISTS comparisons (
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
CREATE INDEX IF NOT EXISTS idx_runs_strategy ON runs(strategy_id);
CREATE INDEX IF NOT EXISTS idx_runs_created ON runs(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_runs_status ON runs(status);
CREATE INDEX IF NOT EXISTS idx_runs_grid_parent ON runs(grid_search_parent_id);
CREATE INDEX IF NOT EXISTS idx_run_configs_symbol ON run_configs(symbol);
CREATE INDEX IF NOT EXISTS idx_trades_run ON trades(run_id);
CREATE INDEX IF NOT EXISTS idx_trades_symbol ON trades(symbol);
CREATE INDEX IF NOT EXISTS idx_tags_run ON tags(run_id);
CREATE INDEX IF NOT EXISTS idx_tags_name ON tags(name);
CREATE INDEX IF NOT EXISTS idx_themes_name ON themes(name);
"""

def init_db():
    """Initialize database with schema."""
    print(f"Initializing database at {DB_PATH}")
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    
    conn = sqlite3.connect(str(DB_PATH))
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()
    print("✅ Database initialized and seeded successfully")

if __name__ == "__main__":
    init_db()
