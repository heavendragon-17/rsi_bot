"""GET /api/strategies — list available strategies."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.schemas import StrategyInfo
from app.repository.backtest.database import SessionLocal
from app.repository.backtest.models import Strategy

router = APIRouter(prefix="/api/strategies", tags=["strategies"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("", response_model=list[StrategyInfo])
def list_strategies(db: Session = Depends(get_db)):
    rows = db.query(Strategy).order_by(Strategy.id).all()
    return [
        StrategyInfo(
            id=int(row.id),
            name=str(row.name),
            description=str(row.description) if row.description else None,
            default_config=dict(row.default_config) if row.default_config else {},
        )
        for row in rows
    ]
