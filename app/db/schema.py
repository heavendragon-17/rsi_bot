"""
Database Schema for Backtest Results
=====================================
Complete schema including existing tables from DATABASE.md + new session/quant tables.
Uses TEXT for monetary values (Decimal precision) and BLOB for timeseries (compressed).
"""
import sqlite3
import json
from typing import Optional
from app.db.connection import get_connection


def init_db(db_path: Optional[str] = None) -> None:
    """
    Initialize the database with all tables.
    Safe to call multiple times (uses CREATE TABLE IF NOT EXISTS).

    Tables created:
    - strategies (from DATABASE.md)
    - themes (from DATABASE.md)
    - sessions (NEW)
    - runs (MODIFIED — includes session_id, run_type, version_number)
    - run_configs (from DATABASE.md)
    - run_results (from DATABASE.md)
    - run_timeseries (from DATABASE.md)
    - trades (from DATABASE.md)
    - tags (from DATABASE.md)
    - comparisons (from DATABASE.md)
    - grid_search_results (NEW)
    - walk_forward_results (NEW)
    - sensitivity_results (NEW)
    - db_settings (NEW)
    """
    with get_connection(db_path) as conn:
        # ============================================
        # STRATEGIES TABLE
        # ============================================
        conn.execute("""
            CREATE TABLE IF NOT EXISTS strategies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                description TEXT,
                default_config JSON NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # ============================================
        # THEMES TABLE
        # ============================================
        conn.execute("""
            CREATE TABLE IF NOT EXISTS themes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                display_name TEXT NOT NULL,
                is_dark BOOLEAN DEFAULT TRUE,
                css_variables JSON NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # ============================================
        # SESSIONS TABLE (NEW)
        # ============================================
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                mode_type TEXT NOT NULL,
                strategy_id INTEGER NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                last_accessed DATETIME,
                status TEXT DEFAULT 'active',
                config_snapshot JSON NOT NULL,
                git_hash TEXT,
                notes TEXT,

                FOREIGN KEY (strategy_id) REFERENCES strategies(id)
            )
        """)

        # ============================================
        # RUNS TABLE (MODIFIED with session support)
        # ============================================
        conn.execute("""
            CREATE TABLE IF NOT EXISTS runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                strategy_id INTEGER NOT NULL,
                session_id TEXT,
                run_type TEXT DEFAULT 'backtest',
                version_number INTEGER DEFAULT 1,
                parent_run_id INTEGER,
                auto_quant_config JSON,
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
                FOREIGN KEY (session_id) REFERENCES sessions(id),
                FOREIGN KEY (parent_run_id) REFERENCES runs(id),
                FOREIGN KEY (grid_search_parent_id) REFERENCES runs(id)
            )
        """)

        # ============================================
        # RUN CONFIGS TABLE
        # ============================================
        conn.execute("""
            CREATE TABLE IF NOT EXISTS run_configs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id INTEGER NOT NULL UNIQUE,
                symbol TEXT NOT NULL,
                symbols_list JSON,
                is_batch_mode BOOLEAN DEFAULT FALSE,
                timeframe TEXT NOT NULL,
                start_date DATE,
                end_date DATE,
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
            )
        """)

        # ============================================
        # RUN RESULTS TABLE
        # ============================================
        conn.execute("""
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
            )
        """)

        # ============================================
        # RUN TIMESERIES TABLE
        # ============================================
        conn.execute("""
            CREATE TABLE IF NOT EXISTS run_timeseries (
                run_id INTEGER PRIMARY KEY,
                equity_curve BLOB,
                drawdown_curve BLOB,
                monthly_returns JSON,

                FOREIGN KEY (run_id) REFERENCES runs(id)
            )
        """)

        # ============================================
        # TRADES TABLE
        # ============================================
        conn.execute("""
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
            )
        """)

        # ============================================
        # TAGS TABLE
        # ============================================
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tags (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                color TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,

                FOREIGN KEY (run_id) REFERENCES runs(id),
                UNIQUE(run_id, name)
            )
        """)

        # ============================================
        # COMPARISONS TABLE
        # ============================================
        conn.execute("""
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
            )
        """)

        # ============================================
        # GRID SEARCH RESULTS TABLE (NEW)
        # ============================================
        conn.execute("""
            CREATE TABLE IF NOT EXISTS grid_search_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id INTEGER NOT NULL,
                session_id TEXT NOT NULL,
                x_param TEXT NOT NULL,
                x_value REAL NOT NULL,
                y_param TEXT NOT NULL,
                y_value REAL NOT NULL,
                net_pnl TEXT,
                net_pnl_pct REAL,
                sharpe_ratio REAL,
                profit_factor REAL,
                win_rate REAL,
                max_drawdown_pct REAL,
                trade_count INTEGER,
                calmar_ratio REAL,
                sortino_ratio REAL,
                above_threshold BOOLEAN DEFAULT FALSE,

                FOREIGN KEY (run_id) REFERENCES runs(id),
                FOREIGN KEY (session_id) REFERENCES sessions(id)
            )
        """)

        # ============================================
        # WALK FORWARD RESULTS TABLE (NEW)
        # ============================================
        conn.execute("""
            CREATE TABLE IF NOT EXISTS walk_forward_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id INTEGER NOT NULL,
                session_id TEXT NOT NULL,
                window_index INTEGER NOT NULL,
                is_start_date DATE,
                is_end_date DATE,
                oos_start_date DATE,
                oos_end_date DATE,
                best_param TEXT,
                best_param_value REAL,
                is_metric_value REAL,
                oos_return_pct REAL,
                is_positive BOOLEAN,

                FOREIGN KEY (run_id) REFERENCES runs(id),
                FOREIGN KEY (session_id) REFERENCES sessions(id)
            )
        """)

        # ============================================
        # SENSITIVITY RESULTS TABLE (NEW)
        # ============================================
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sensitivity_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id INTEGER NOT NULL,
                session_id TEXT NOT NULL,
                param_name TEXT NOT NULL,
                low_value REAL,
                base_value REAL,
                high_value REAL,
                low_metric REAL,
                base_metric REAL,
                high_metric REAL,
                metric_name TEXT,
                sensitivity_level TEXT,

                FOREIGN KEY (run_id) REFERENCES runs(id),
                FOREIGN KEY (session_id) REFERENCES sessions(id)
            )
        """)

        # ============================================
        # DB SETTINGS TABLE (NEW)
        # ============================================
        conn.execute("""
            CREATE TABLE IF NOT EXISTS db_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)

        # ============================================
        # MIGRATIONS: Add columns to existing tables
        # Must run BEFORE index creation so new columns exist
        # ============================================
        _migrate_runs_table(conn)

        # ============================================
        # INDEXES
        # ============================================
        # Existing indexes
        conn.execute("CREATE INDEX IF NOT EXISTS idx_runs_strategy ON runs(strategy_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_runs_created ON runs(created_at DESC)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_runs_status ON runs(status)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_runs_grid_parent ON runs(grid_search_parent_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_run_configs_symbol ON run_configs(symbol)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_trades_run ON trades(run_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_trades_symbol ON trades(symbol)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_tags_run ON tags(run_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_tags_name ON tags(name)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_themes_name ON themes(name)")

        # New indexes for sessions and quant tables
        conn.execute("CREATE INDEX IF NOT EXISTS idx_sessions_mode ON sessions(mode_type)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_sessions_strategy ON sessions(strategy_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_sessions_created ON sessions(created_at DESC)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_runs_session ON runs(session_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_runs_type ON runs(run_type)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_runs_version ON runs(version_number)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_gs_results_run ON grid_search_results(run_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_gs_results_session ON grid_search_results(session_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_wf_results_run ON walk_forward_results(run_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_sens_results_run ON sensitivity_results(run_id)")


def _migrate_runs_table(conn) -> None:
    """
    Add Phase 0/1 columns to the existing runs table if they are missing.
    SQLite does not support ALTER TABLE IF NOT EXISTS, so we check PRAGMA table_info.
    """
    cursor = conn.execute("PRAGMA table_info(runs)")
    existing_columns = {row[1] for row in cursor.fetchall()}

    migrations = [
        ("session_id", "TEXT REFERENCES sessions(id)"),
        ("run_type", "TEXT DEFAULT 'backtest'"),
        ("version_number", "INTEGER DEFAULT 1"),
        ("parent_run_id", "INTEGER REFERENCES runs(id)"),
        ("auto_quant_config", "TEXT"),
        ("git_hash", "TEXT"),
        ("version", "TEXT"),
        ("is_grid_search", "BOOLEAN DEFAULT FALSE"),
        ("grid_search_parent_id", "INTEGER"),
        ("grid_search_total", "INTEGER"),
        ("grid_search_completed", "INTEGER"),
    ]

    for col_name, col_def in migrations:
        if col_name not in existing_columns:
            conn.execute(f"ALTER TABLE runs ADD COLUMN {col_name} {col_def}")


def seed_defaults(db_path: Optional[str] = None) -> None:
    """
    Insert default strategies, themes, and settings.
    Uses INSERT OR IGNORE to be idempotent.
    """
    with get_connection(db_path) as conn:
        # Seed rsi_no_retest strategy
        conn.execute("""
            INSERT OR IGNORE INTO strategies (name, description, default_config) VALUES (?, ?, ?)
        """, (
            'rsi_no_retest',
            'RSI strategy without retest confirmation',
            json.dumps({
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
            })
        ))

        # Seed cyberpunk_neon theme
        conn.execute("""
            INSERT OR IGNORE INTO themes (name, display_name, is_dark, css_variables) VALUES (?, ?, ?, ?)
        """, (
            'cyberpunk_neon',
            'Cyberpunk Neon',
            True,
            json.dumps({
                "--bg-primary": "#0F172A",
                "--bg-secondary": "#1E293B",
                "--bg-surface": "rgba(30, 41, 59, 0.4)",
                "--text-primary": "#F8FAFC",
                "--text-secondary": "#94A3B8",
                "--text-muted": "#64748B",
                "--accent": "#8B5CF6"
            })
        ))

        # Seed default DB settings
        conn.execute("""
            INSERT OR IGNORE INTO db_settings (key, value) VALUES (?, ?)
        """, ('max_db_size_mb', '0'))  # 0 = unlimited
