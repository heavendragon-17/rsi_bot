import json
import zlib
from decimal import Decimal
from typing import List, Dict, Optional, Any
from sqlalchemy import create_engine, select, update
from sqlalchemy.orm import sessionmaker, Session
from .models import Run, RunResult, RunTimeseries, Trade, Theme

DEFAULT_DB_PATH = "sqlite:///data/backtest.db"

class BacktestRepository:
    def __init__(self, db_url: str = DEFAULT_DB_PATH):
        self.engine = create_engine(db_url)
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)

    def _get_session(self) -> Session:
        return self.SessionLocal()

    def save_run(self, run_data: dict) -> int:
        """Save run metadata and return ID."""
        with self._get_session() as session:
            # Ensure config is JSON string
            config_json = run_data.get("config_json", "{}")
            if isinstance(config_json, dict):
                config_json = json.dumps(config_json)

            run = Run(
                strategy_name=run_data["strategy_name"],
                symbol=run_data["symbol"],
                timeframe=run_data["timeframe"],
                start_date=run_data["start_date"],
                end_date=run_data["end_date"],
                created_at=run_data.get("created_at", ""),
                config_json=config_json
            )
            session.add(run)
            session.commit()
            session.refresh(run)
            return run.id

    def get_run(self, run_id: int) -> Optional[dict]:
        """Get run by ID."""
        with self._get_session() as session:
            run = session.get(Run, run_id)
            if not run:
                return None
            return {
                "id": run.id,
                "strategy_name": run.strategy_name,
                "symbol": run.symbol,
                "timeframe": run.timeframe,
                "start_date": run.start_date,
                "end_date": run.end_date,
                "created_at": run.created_at,
                "config_json": json.loads(run.config_json) if run.config_json else {}
            }

    def get_all_runs(self) -> List[dict]:
        """Get all runs."""
        with self._get_session() as session:
            runs = session.execute(select(Run)).scalars().all()
            return [
                {
                    "id": run.id,
                    "strategy_name": run.strategy_name,
                    "symbol": run.symbol,
                    "timeframe": run.timeframe,
                    "start_date": run.start_date,
                    "end_date": run.end_date,
                    "created_at": run.created_at,
                    # config_json might be heavy, maybe skip?
                    # Implementation usually fetches all unless specified otherwise.
                    "config_json": json.loads(run.config_json) if run.config_json else {}
                }
                for run in runs
            ]

    def save_run_results(self, run_id: int, results: dict):
        """Save performance metrics."""
        with self._get_session() as session:
            # Handle Decimal -> str conversion
            metrics_json = results.get("metrics_json", "{}")
            if isinstance(metrics_json, dict):
                metrics_json = json.dumps(metrics_json, default=str)

            run_result = RunResult(
                run_id=run_id,
                total_profit=str(results["total_profit"]),
                win_rate=results.get("win_rate"),
                total_trades=results.get("total_trades"),
                profit_factor=results.get("profit_factor"),
                max_drawdown=str(results.get("max_drawdown", "0")),
                sharpe_ratio=results.get("sharpe_ratio"),
                metrics_json=metrics_json
            )
            session.add(run_result)
            session.commit()

    def get_run_results(self, run_id: int) -> Optional[dict]:
        """Get results for run."""
        with self._get_session() as session:
            result = session.execute(select(RunResult).where(RunResult.run_id == run_id)).scalar_one_or_none()
            if not result:
                return None
            return {
                "total_profit": Decimal(result.total_profit),
                "win_rate": result.win_rate,
                "total_trades": result.total_trades,
                "profit_factor": result.profit_factor,
                "max_drawdown": Decimal(result.max_drawdown),
                "sharpe_ratio": result.sharpe_ratio,
                "metrics_json": json.loads(result.metrics_json) if result.metrics_json else {}
            }

    def save_trades(self, run_id: int, trades: List[dict]):
        """Save list of trades."""
        with self._get_session() as session:
            trade_objs = []
            for t in trades:
                trade_objs.append(Trade(
                    run_id=run_id,
                    entry_time=t["entry_time"],
                    exit_time=t.get("exit_time"),
                    entry_price=str(t["entry_price"]),
                    exit_price=str(t.get("exit_price")) if t.get("exit_price") is not None else None,
                    quantity=str(t["quantity"]),
                    side=t["side"],
                    pnl=str(t.get("pnl")) if t.get("pnl") is not None else None,
                    exit_reason=t.get("exit_reason")
                ))
            session.add_all(trade_objs)
            session.commit()

    def get_trades(self, run_id: int) -> List[dict]:
        """Get trades for run."""
        with self._get_session() as session:
            trades = session.execute(select(Trade).where(Trade.run_id == run_id)).scalars().all()
            return [
                {
                    "id": t.id,
                    "entry_time": t.entry_time,
                    "exit_time": t.exit_time,
                    "entry_price": Decimal(t.entry_price),
                    "exit_price": Decimal(t.exit_price) if t.exit_price else None,
                    "quantity": Decimal(t.quantity),
                    "side": t.side,
                    "pnl": Decimal(t.pnl) if t.pnl else None,
                    "exit_reason": t.exit_reason
                }
                for t in trades
            ]

    def save_timeseries(self, run_id: int, equity: list, drawdown: list):
        """Compress and save timeseries data."""
        with self._get_session() as session:
            # Compress using zlib
            equity_json = json.dumps(equity, default=str)
            equity_blob = zlib.compress(equity_json.encode('utf-8'))

            drawdown_json = json.dumps(drawdown, default=str)
            drawdown_blob = zlib.compress(drawdown_json.encode('utf-8'))

            ts = RunTimeseries(
                run_id=run_id,
                equity_curve=equity_blob,
                drawdown_curve=drawdown_blob
            )
            session.add(ts)
            session.commit()

    def get_timeseries(self, run_id: int) -> dict:
        """Decompress and return timeseries data."""
        with self._get_session() as session:
            ts = session.execute(select(RunTimeseries).where(RunTimeseries.run_id == run_id)).scalar_one_or_none()
            if not ts:
                return {"equity_curve": [], "drawdown_curve": []}

            equity_curve = []
            if ts.equity_curve:
                equity_curve = json.loads(zlib.decompress(ts.equity_curve).decode('utf-8'))

            drawdown_curve = []
            if ts.drawdown_curve:
                drawdown_curve = json.loads(zlib.decompress(ts.drawdown_curve).decode('utf-8'))

            return {
                "equity_curve": equity_curve,
                "drawdown_curve": drawdown_curve
            }

    def get_themes(self) -> List[dict]:
        """Get all themes."""
        with self._get_session() as session:
            themes = session.execute(select(Theme)).scalars().all()
            return [
                {
                    "name": t.name,
                    "is_active": t.is_active,
                    "colors": json.loads(t.colors_json)
                }
                for t in themes
            ]

    def get_active_theme(self) -> Optional[dict]:
        """Get active theme."""
        with self._get_session() as session:
            theme = session.execute(select(Theme).where(Theme.is_active == True)).scalar_one_or_none()
            if not theme:
                return None
            return {
                "name": theme.name,
                "is_active": theme.is_active,
                "colors": json.loads(theme.colors_json)
            }

    def set_active_theme(self, theme_name: str):
        """Set active theme."""
        with self._get_session() as session:
            # Deactivate all
            session.execute(update(Theme).values(is_active=False))
            # Activate one
            session.execute(update(Theme).where(Theme.name == theme_name).values(is_active=True))
            session.commit()
