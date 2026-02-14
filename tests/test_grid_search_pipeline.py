"""
Integration tests for Phase 2: Grid Search Pipeline End-to-End
==============================================================
Tests the full flow: _run_single_combo → executor → DB → API responses.

Run:
    conda run -n rsi python -m pytest tests/test_grid_search_pipeline.py -v
"""
import os
import sys
import pytest

# Add project root to path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)


# ─────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────

@pytest.fixture(scope="module", autouse=True)
def setup_prod_db():
    """Ensure production DB is initialized."""
    from app.db.schema import init_db, seed_defaults
    init_db()
    seed_defaults()
    yield


@pytest.fixture(scope="module")
def test_session_id():
    """Create a test session in the production DB."""
    from app.db.connection import get_connection
    from app.db.repositories import session_repo
    with get_connection() as conn:
        session_id = session_repo.create_session(
            conn,
            mode_type="grid_search",
            strategy_id=1,
            config_snapshot={"symbol": "1INCH/USDT", "timeframe": "15m"},
        )
    return session_id


@pytest.fixture(scope="module")
def base_config():
    """Minimal valid config for 1INCH/USDT 15m grid search."""
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


@pytest.fixture(scope="module")
def grid_config_2x2():
    """2×2 grid (4 combinations) to keep runtime fast."""
    return {
        "x_param": "rsi_period",
        "x_min": 14,
        "x_max": 16,
        "x_step": 2,
        "y_param": "ema_fast",
        "y_min": 9,
        "y_max": 11,
        "y_step": 2,
        "metric": "net_pnl",
    }


# ─────────────────────────────────────────────
# T1: _run_single_combo
# ─────────────────────────────────────────────

class TestRunSingleCombo:
    def test_returns_metrics_dict(self, base_config):
        """_run_single_combo returns a dict with expected metric keys."""
        from app.engine.grid_search_executor import _run_single_combo

        combo_config = dict(base_config)
        combo_config["x_param"] = "rsi_period"
        combo_config["x_value"] = 14
        combo_config["y_param"] = "ema_fast"
        combo_config["y_value"] = 9

        result = _run_single_combo(combo_config)

        assert "error" not in result, f"Combo returned error: {result.get('error')}"
        assert result["x_param"] == "rsi_period"
        assert result["x_value"] == 14
        assert result["y_param"] == "ema_fast"
        assert result["y_value"] == 9

    def test_has_required_metric_keys(self, base_config):
        """Result dict contains all required metric fields."""
        from app.engine.grid_search_executor import _run_single_combo

        combo_config = dict(base_config)
        combo_config["x_param"] = "rsi_period"
        combo_config["x_value"] = 14
        combo_config["y_param"] = "ema_fast"
        combo_config["y_value"] = 9

        result = _run_single_combo(combo_config)

        for key in ("net_pnl", "net_pnl_pct", "sharpe_ratio", "profit_factor",
                    "win_rate", "max_drawdown_pct", "trade_count",
                    "calmar_ratio", "sortino_ratio", "above_threshold"):
            assert key in result, f"Missing key: {key}"

    def test_above_threshold_logic(self, base_config):
        """above_threshold is True when sharpe_ratio > 0."""
        from app.engine.grid_search_executor import _run_single_combo

        combo_config = dict(base_config)
        combo_config["x_param"] = "rsi_period"
        combo_config["x_value"] = 14
        combo_config["y_param"] = "ema_fast"
        combo_config["y_value"] = 9

        result = _run_single_combo(combo_config)
        assert bool(result["above_threshold"]) == (result["sharpe_ratio"] > 0)


# ─────────────────────────────────────────────
# T2: Combination generator
# ─────────────────────────────────────────────

class TestGenerateCombinations:
    def test_2x2_generates_4_combos(self, base_config, grid_config_2x2):
        """2×2 grid generates exactly 4 combinations."""
        from app.engine.grid_search_executor import _generate_combinations
        combos = _generate_combinations(base_config, grid_config_2x2)
        assert len(combos) == 4

    def test_combo_has_param_overrides(self, base_config, grid_config_2x2):
        """Each combo has x_param and y_param overridden in params."""
        from app.engine.grid_search_executor import _generate_combinations
        combos = _generate_combinations(base_config, grid_config_2x2)

        for combo in combos:
            assert combo["x_param"] == "rsi_period"
            assert combo["y_param"] == "ema_fast"
            assert combo["params"]["rsi_period"] == combo["x_value"]
            assert combo["params"]["ema_fast"] == combo["y_value"]

    def test_base_config_not_mutated(self, base_config, grid_config_2x2):
        """_generate_combinations does not mutate base_config."""
        from app.engine.grid_search_executor import _generate_combinations
        original_rsi = base_config["params"]["rsi_period"]
        _generate_combinations(base_config, grid_config_2x2)
        assert base_config["params"]["rsi_period"] == original_rsi


# ─────────────────────────────────────────────
# T3: Full grid search executor (sync path)
# ─────────────────────────────────────────────

class TestGridSearchExecutorSync:
    def test_2x2_creates_db_records(self, test_session_id, base_config, grid_config_2x2):
        """2×2 grid search produces 4 rows in grid_search_results."""
        import asyncio
        from app.db.connection import get_connection
        from app.db.repositories import run_repo, grid_search_repo
        from app.api.sse import get_queue
        from app.engine.grid_search_executor import _run_grid_search_sync

        # Create run record
        with get_connection() as conn:
            run_id = run_repo.create_run(
                conn,
                strategy_id=1,
                session_id=test_session_id,
                run_type="grid_search",
            )

        loop = asyncio.new_event_loop()
        try:
            get_queue(run_id)
            result = _run_grid_search_sync(
                run_id, test_session_id, base_config, grid_config_2x2, loop
            )
        finally:
            loop.close()

        assert "error" not in result, f"Executor returned error: {result.get('error')}"
        assert result["status"] == "completed"
        assert result["total_combos"] == 4

        # Verify DB rows
        with get_connection() as conn:
            rows = grid_search_repo.get_results(conn, run_id)
        assert len(rows) == 4, f"Expected 4 rows, got {len(rows)}"

    def test_run_marked_completed(self, test_session_id, base_config, grid_config_2x2):
        """Run status is 'completed' after grid search finishes."""
        import asyncio
        from app.db.connection import get_connection
        from app.db.repositories import run_repo
        from app.api.sse import get_queue
        from app.engine.grid_search_executor import _run_grid_search_sync

        with get_connection() as conn:
            run_id = run_repo.create_run(
                conn, strategy_id=1, session_id=test_session_id, run_type="grid_search"
            )

        loop = asyncio.new_event_loop()
        try:
            get_queue(run_id)
            _run_grid_search_sync(run_id, test_session_id, base_config, grid_config_2x2, loop)
        finally:
            loop.close()

        with get_connection() as conn:
            run = run_repo.get_run(conn, run_id)
        assert run["status"] == "completed"


# ─────────────────────────────────────────────
# T4: API endpoint smoke tests
# ─────────────────────────────────────────────

class TestGridSearchAPISmoke:
    @pytest.fixture(autouse=True)
    def skip_if_no_httpx(self):
        pytest.importorskip("httpx")

    def test_post_run_returns_run_id(self, test_session_id, base_config):
        """POST /api/grid-search/run returns run_id and total_combinations."""
        from fastapi.testclient import TestClient
        from app.api.server import app

        client = TestClient(app)
        resp = client.post("/api/grid-search/run", json={
            "session_id": test_session_id,
            "config": base_config,
            "grid": {
                "x_param": "rsi_period",
                "x_min": 14, "x_max": 16, "x_step": 2,
                "y_param": "ema_fast",
                "y_min": 9, "y_max": 11, "y_step": 2,
                "metric": "net_pnl",
            }
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "run_id" in data
        assert data["run_id"] > 0
        assert data["total_combinations"] == 4
        assert data["status"] == "pending"

    def test_get_nonexistent_run_404(self):
        """GET /api/grid-search/999999 returns 404."""
        from fastapi.testclient import TestClient
        from app.api.server import app

        client = TestClient(app)
        resp = client.get("/api/grid-search/999999")
        assert resp.status_code == 404

    def test_get_results_after_sync_run(self, test_session_id, base_config, grid_config_2x2):
        """GET /api/grid-search/{run_id} returns results after sync execution."""
        import asyncio
        from app.db.connection import get_connection
        from app.db.repositories import run_repo
        from app.api.sse import get_queue
        from app.engine.grid_search_executor import _run_grid_search_sync
        from fastapi.testclient import TestClient
        from app.api.server import app

        # Run synchronously
        with get_connection() as conn:
            run_id = run_repo.create_run(
                conn, strategy_id=1, session_id=test_session_id, run_type="grid_search"
            )
        loop = asyncio.new_event_loop()
        try:
            get_queue(run_id)
            _run_grid_search_sync(run_id, test_session_id, base_config, grid_config_2x2, loop)
        finally:
            loop.close()

        # Query via API
        client = TestClient(app)
        resp = client.get(f"/api/grid-search/{run_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert "results" in data
        assert len(data["results"]) == 4
        assert data["run_status"] == "completed"
