"""
Integration tests for Phase 1: Backtest Pipeline End-to-End
============================================================
Tests the full flow: executor → DB → API responses.

Run:
    conda run -n rsi python -m pytest tests/test_backtest_pipeline.py -v
"""
import os
import sys
import pytest

# Add project root to path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

# Use the production DB — executor hardcodes get_connection() (no path arg)
# so all executor tests must use the same DB.

# ─────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────

@pytest.fixture(scope="module", autouse=True)
def setup_prod_db():
    """Ensure production DB is initialized with current schema (including migrations)."""
    from app.db.schema import init_db, seed_defaults
    init_db()
    seed_defaults()
    yield


@pytest.fixture(scope="module")
def test_session_id():
    """Create a test session in the production DB and return its ID."""
    from app.db.connection import get_connection
    from app.db.repositories import session_repo
    with get_connection() as conn:
        session_id = session_repo.create_session(
            conn,
            mode_type="single",
            strategy_id=1,
            config_snapshot={"symbol": "1INCH/USDT", "timeframe": "15m"},
        )
    return session_id


@pytest.fixture(scope="module")
def sample_config():
    """Minimal valid config for 1INCH/USDT 15m (has more data for signal generation)."""
    return {
        "symbol": "1INCH/USDT",
        "timeframe": "15m",
        "strategy": "rsi_no_retest",
        "capital": "10000",
        "leverage": "1",
        "riskPercent": "1",
        "params": {
            "rsi_period": 14,
            "ema_fast": 9,
            "ema_slow": 21,
            "tp1_rr": 1.5,
            "tp2_rr": 3.0,
            "sl_buffer_pct": 1.0,
            "overbought": 70,
            "oversold": 30,
        },
    }


# ─────────────────────────────────────────────
# T1: Symbol normalization
# ─────────────────────────────────────────────

class TestSymbolNormalization:
    def test_slash_usdt(self):
        from app.engine.executor import normalize_symbol
        assert normalize_symbol("BTC/USDT") == "BTC"

    def test_slash_usd(self):
        from app.engine.executor import normalize_symbol
        assert normalize_symbol("BTC/USD") == "BTC"

    def test_no_slash_usdt(self):
        from app.engine.executor import normalize_symbol
        assert normalize_symbol("BTCUSDT") == "BTC"

    def test_bare_symbol(self):
        from app.engine.executor import normalize_symbol
        assert normalize_symbol("BTC") == "BTC"

    def test_lowercase(self):
        from app.engine.executor import normalize_symbol
        assert normalize_symbol("eth") == "ETH"

    def test_eth_usdt(self):
        from app.engine.executor import normalize_symbol
        assert normalize_symbol("ETH/USDT") == "ETH"


# ─────────────────────────────────────────────
# T2: Data path resolution
# ─────────────────────────────────────────────

class TestDataPath:
    def test_1inch_path_exists(self):
        from app.engine.executor import resolve_data_path
        path = resolve_data_path("1INCH/USDT", "15m")
        assert os.path.exists(path), f"Data file not found: {path}"

    def test_bare_symbol_same_path(self):
        from app.engine.executor import resolve_data_path
        path1 = resolve_data_path("1INCH/USDT", "15m")
        path2 = resolve_data_path("1INCH", "15m")
        assert path1 == path2

    def test_no_slash_same_path(self):
        from app.engine.executor import resolve_data_path
        path1 = resolve_data_path("1INCH/USDT", "15m")
        path2 = resolve_data_path("1INCHUSDT", "15m")
        assert path1 == path2


# ─────────────────────────────────────────────
# T3: Config builder
# ─────────────────────────────────────────────

class TestConfigBuilder:
    def test_symbols_field(self, sample_config):
        from app.engine.executor import build_engine_config
        cfg = build_engine_config(sample_config)
        assert "symbols" in cfg
        assert cfg["symbols"] == ["1INCH/USDT"]

    def test_initial_balance(self, sample_config):
        from app.engine.executor import build_engine_config
        cfg = build_engine_config(sample_config)
        assert cfg["backtest"]["initial_balance"] == 10000.0

    def test_risk_per_trade(self, sample_config):
        from app.engine.executor import build_engine_config
        cfg = build_engine_config(sample_config)
        assert cfg["risk"]["risk_per_trade_pct"] == pytest.approx(0.01)


# ─────────────────────────────────────────────
# T4: Executor — synchronous run
# ─────────────────────────────────────────────

class TestExecutorSync:
    def test_run_creates_db_records(self, test_session_id, sample_config):
        """Run the synchronous worker and verify DB records are created."""
        import asyncio
        from app.db.connection import get_connection
        from app.db.repositories import run_repo, session_repo

        # Create run record
        with get_connection() as conn:
            run_id = run_repo.create_run(
                conn,
                strategy_id=1,
                session_id=test_session_id,
                run_type="backtest",
            )

        assert run_id is not None and run_id > 0

        # Run synchronous worker (with a fake loop for event publishing)
        loop = asyncio.new_event_loop()
        try:
            # Pre-create SSE queue
            from app.api.sse import get_queue
            get_queue(run_id)

            from app.engine.executor import _run_backtest_sync
            result = _run_backtest_sync(run_id, test_session_id, sample_config, loop)
        finally:
            loop.close()

        # Should not be an error result
        assert "error" not in result, f"Executor returned error: {result.get('error')}"
        assert result["status"] == "completed"
        assert result["run_id"] == run_id

        # Verify DB has the run in completed state
        with get_connection() as conn:
            run = run_repo.get_run(conn, run_id)
            assert run is not None
            assert run["status"] == "completed"

            # Verify results row exists
            cursor = conn.execute(
                "SELECT total_trades, win_rate, sharpe_ratio FROM run_results WHERE run_id = ?",
                (run_id,)
            )
            row = cursor.fetchone()
            assert row is not None, "run_results row not found"
            total_trades, win_rate, sharpe_ratio = row
            assert total_trades >= 0, "total_trades must be non-negative"
            # win_rate is 0 when no trades fired (small test CSV)
            assert win_rate is None or 0 <= win_rate <= 100, f"Win rate out of range: {win_rate}"

    def test_metrics_keys_in_result(self, test_session_id, sample_config):
        """Verify the returned metrics dict has expected keys."""
        import asyncio
        from app.db.connection import get_connection
        from app.db.repositories import run_repo
        from app.api.sse import get_queue
        from app.engine.executor import _run_backtest_sync

        with get_connection() as conn:
            run_id = run_repo.create_run(conn, strategy_id=1, session_id=test_session_id, run_type="backtest")

        loop = asyncio.new_event_loop()
        try:
            get_queue(run_id)
            result = _run_backtest_sync(run_id, test_session_id, sample_config, loop)
        finally:
            loop.close()

        assert "metrics" in result
        metrics = result["metrics"]
        for key in ("net_profit", "net_profit_pct", "total_trades", "win_rate",
                    "profit_factor", "sharpe_ratio", "max_drawdown_pct"):
            assert key in metrics, f"Missing metrics key: {key}"


# ─────────────────────────────────────────────
# T5: API endpoint smoke tests
# ─────────────────────────────────────────────

class TestAPISmoke:
    """
    Smoke tests using httpx TestClient (no live server needed).
    Skipped if httpx not available.
    """

    @pytest.fixture(autouse=True)
    def skip_if_no_httpx(self):
        pytest.importorskip("httpx")

    def test_health_endpoint(self):
        from fastapi.testclient import TestClient
        from app.api.server import app
        client = TestClient(app)
        resp = client.get("/api/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_get_nonexistent_run(self):
        from fastapi.testclient import TestClient
        from app.api.server import app
        client = TestClient(app)
        resp = client.get("/api/backtest/999999")
        assert resp.status_code == 404
