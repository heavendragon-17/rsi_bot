"""Tests for history/listing routes (M13 coverage gap)."""

from datetime import date, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.main import app
from app.api.routes import history as history_mod
from app.repository.backtest.database import Base
from app.repository.backtest.models import Run, RunConfig, Strategy

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


app.dependency_overrides[history_mod.get_db] = override_get_db
client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


def _seed_strategy(db, name="rsi_no_retest"):
    s = Strategy(name=name, description="Test", default_config={})
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


def _seed_run(db, strategy_id, symbol="BTC/USDT", status="completed"):
    run = Run(strategy_id=strategy_id, status=status, created_at=datetime.utcnow())
    db.add(run)
    db.commit()
    db.refresh(run)
    cfg = RunConfig(
        run_id=run.id,
        symbol=symbol,
        timeframe="1h",
        start_date=date(2023, 1, 1),
        end_date=date(2023, 6, 1),
        params={},
    )
    db.add(cfg)
    db.commit()
    return run


class TestHistoryEmpty:
    def test_empty_returns_zero(self):
        resp = client.get("/api/history")
        assert resp.status_code == 200
        data = resp.json()
        assert data["runs"] == []
        assert data["total"] == 0


class TestHistoryPagination:
    def test_pagination(self):
        db = TestSession()
        strat = _seed_strategy(db)
        for _ in range(3):
            _seed_run(db, strat.id)
        db.close()

        resp = client.get("/api/history", params={"page": 1, "limit": 2})
        data = resp.json()
        assert len(data["runs"]) == 2
        assert data["total"] == 3
        assert data["pages"] == 2


class TestHistoryFilter:
    def test_filter_by_strategy(self):
        db = TestSession()
        s1 = _seed_strategy(db, "strat_a")
        s2 = _seed_strategy(db, "strat_b")
        _seed_run(db, s1.id)
        _seed_run(db, s2.id)
        db.close()

        resp = client.get("/api/history", params={"strategy": "strat_a"})
        data = resp.json()
        assert data["total"] == 1
        assert data["runs"][0]["strategy_name"] == "strat_a"


class TestDeleteRun:
    def test_delete_run(self):
        db = TestSession()
        strat = _seed_strategy(db)
        run = _seed_run(db, strat.id)
        run_id = run.id
        db.close()

        resp = client.delete(f"/api/history/{run_id}")
        assert resp.status_code == 200
        assert resp.json()["deleted"] is True

    def test_delete_nonexistent(self):
        resp = client.delete("/api/history/99999")
        assert resp.status_code == 404
