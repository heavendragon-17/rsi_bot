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
            id=row.id,
            name=row.name,
            description=row.description,
            default_config=row.default_config or {},
        )
        for row in rows
    ]
