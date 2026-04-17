from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.main import app
from app.api.routes.backtest_run import get_db
from app.repository.backtest.database import Base

# Use an in-memory SQLite database for testing
SQLALCHEMY_DATABASE_URL = "sqlite:///./test.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()


# Override get_db in all three route modules
from app.api.routes import backtest_results  # noqa: E402

app.dependency_overrides[get_db] = override_get_db
app.dependency_overrides[backtest_results.get_db] = override_get_db

client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
    # Seed a strategy
    from app.repository.backtest.models import Strategy

    db = TestingSessionLocal()
    if not db.query(Strategy).filter_by(name="rsi_no_retest").first():
        db.add(Strategy(name="rsi_no_retest", description="Test Strat", default_config={}))
        db.commit()
    db.close()
    yield
    Base.metadata.drop_all(bind=engine)


@patch("app.backtest.service.os.path.exists")
@patch("app.backtest.service.exc_mod.submit_backtest")
def test_run_backtest_endpoint(mock_submit, mock_exists):
    # Mock file exists check for market data
    mock_exists.return_value = True

    # Payload for the backtest run
    payload = {
        "symbol": "BTC/USDT",
        "timeframe": "1h",
        "strategy": "rsi_no_retest",
        "start_date": "2023-01-01",
        "end_date": "2023-01-02",
        "initial_capital": "10000",
        "leverage": 1,
        "risk_per_trade_pct": "1.0",
        "params": {},
    }

    response = client.post("/api/backtest/run", json=payload)

    assert response.status_code == 201
    data = response.json()
    assert "run_id" in data
    assert data["status"] == "running"

    # Verify that the job was submitted
    assert mock_submit.called

    # Now check if we can get the run details
    run_id = data["run_id"]
    response = client.get(f"/api/backtest/{run_id}")
    assert response.status_code == 200
    run_data = response.json()
    assert run_data["id"] == run_id
    assert run_data["symbol"] == "BTC/USDT"


@patch("app.backtest.service.os.path.exists")
@patch("app.backtest.service.exc_mod.submit_backtest")
def test_run_backtest_with_explicit_mode(mock_submit, mock_exists):
    """Test that explicit mode='single' works."""
    mock_exists.return_value = True

    payload = {
        "mode": "single",
        "symbol": "ETH/USDT",
        "timeframe": "5m",
        "strategy": "rsi_no_retest",
        "start_date": "2023-01-01",
        "end_date": "2023-01-02",
    }

    response = client.post("/api/backtest/run", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "running"


def test_run_backtest_missing_data_file():
    """Test 400 when CSV data file doesn't exist."""
    payload = {
        "symbol": "NONEXIST/USDT",
        "timeframe": "1h",
        "strategy": "rsi_no_retest",
        "start_date": "2023-01-01",
        "end_date": "2023-01-02",
    }

    response = client.post("/api/backtest/run", json=payload)
    assert response.status_code == 400
    assert "Data file not found" in response.json()["detail"]


def test_run_backtest_unknown_strategy():
    """Test 400 for unknown strategy name."""
    payload = {
        "symbol": "BTC/USDT",
        "timeframe": "1h",
        "strategy": "nonexistent_strategy",
        "start_date": "2023-01-01",
        "end_date": "2023-01-02",
    }

    response = client.post("/api/backtest/run", json=payload)
    assert response.status_code == 400
    assert "Unknown strategy" in response.json()["detail"]


def test_get_nonexistent_run():
    """Test 404 for missing run."""
    response = client.get("/api/backtest/99999")
    assert response.status_code == 404


@patch("app.backtest.service.os.path.exists")
@patch("app.backtest.service.exc_mod.submit_backtest")
def test_run_backtest_portfolio_mode(mock_submit, mock_exists):
    """Test mode='portfolio' with symbols list (multi-symbol backtest)."""
    mock_exists.return_value = True

    payload = {
        "mode": "portfolio",
        "symbols": ["BTC/USDT", "ETH/USDT"],
        "timeframe": "1h",
        "strategy": "rsi_no_retest",
        "start_date": "2023-01-01",
        "end_date": "2023-01-02",
    }

    response = client.post("/api/backtest/run", json=payload)
    assert response.status_code == 201
    assert response.json()["status"] == "running"


@patch("app.backtest.service.os.path.exists")
@patch("app.backtest.service.exc_mod.submit_backtest")
def test_run_backtest_tick_replay_mode(mock_submit, mock_exists):
    """Test mode='tick_replay' with symbol + tick_data_path."""
    mock_exists.return_value = True

    payload = {
        "mode": "tick_replay",
        "symbol": "BTC/USDT",
        "timeframe": "1m",
        "strategy": "rsi_no_retest",
        "start_date": "2023-01-01",
        "end_date": "2023-01-02",
        "tick_data_path": "/data/ticks/BTCUSDT.csv",
    }

    response = client.post("/api/backtest/run", json=payload)
    assert response.status_code == 201
    assert response.json()["status"] == "running"


def test_batch_mode_requires_symbols():
    """Test 422 when mode='batch' but symbols not provided."""
    payload = {
        "mode": "batch",
        "timeframe": "1h",
        "strategy": "rsi_no_retest",
        "start_date": "2023-01-01",
        "end_date": "2023-01-02",
    }

    response = client.post("/api/backtest/run", json=payload)
    assert response.status_code == 422
