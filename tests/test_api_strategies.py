"""Tests for strategy info routes (M13 coverage gap)."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.main import app
from app.api.routes import strategies as strat_mod
from app.repository.backtest.database import Base
from app.repository.backtest.models import Strategy

engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    db = TestSession()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[strat_mod.get_db] = override_get_db
client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
    db = TestSession()
    if not db.query(Strategy).filter_by(name="rsi_no_retest").first():
        db.add(Strategy(name="rsi_no_retest", description="Short strat", default_config={"tp1_rr": 1.0}))
        db.add(Strategy(name="rsi_long", description="Long strat", default_config={}))
        db.commit()
    db.close()
    yield
    Base.metadata.drop_all(bind=engine)


class TestListStrategies:
    def test_returns_seeded_strategies(self):
        resp = client.get("/api/strategies")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 2
        names = [s["name"] for s in data]
        assert "rsi_no_retest" in names

    def test_strategy_has_expected_fields(self):
        resp = client.get("/api/strategies")
        item = resp.json()[0]
        assert "id" in item
        assert "name" in item
        assert "description" in item
        assert "default_config" in item
        assert isinstance(item["default_config"], dict)
