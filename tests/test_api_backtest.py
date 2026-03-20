import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch
import os
import json

from app.api.main import app
from app.api.routes.backtest_run import get_db
from app.repository.backtest.database import Base
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine

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

app.dependency_overrides[get_db] = override_get_db

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

@patch("app.api.routes.backtest.os.path.exists")
@patch("app.api.routes.backtest.exc_mod.submit_backtest")
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
        "initial_capital": 10000,
        "leverage": 1,
        "risk_per_trade_pct": 1.0,
        "params": {}
    }
    
    response = client.post("/api/backtest/run", json=payload)
    
    assert response.status_code == 200 # App returns 200 based on code flow
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
