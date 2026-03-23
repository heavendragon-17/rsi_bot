"""
Backtest Engine (PR7: Unified Engine with Event Source Pattern)
===============================================================
Subclasses the unified Engine. BacktestEngine adds:
  - Pre-computation of indicators across the full dataset (O(n) efficiency)
  - MockExchange wick-based SL/TP fill checking on each candle
  - End-of-data position closing for accurate final balance reporting
  - Progress callbacks (on_progress) for API/UI streaming
  - compute_results() — all metric computation lives here (not in Reporter)
  - Backtest-specific logging (start/complete messages)

All action dispatch and strategy analysis are handled by the base Engine.
"""

import numpy as np
import pandas as pd
import structlog

from app.backtest.engine.curves import build_drawdown_curve_dated, build_equity_curve_dated
from app.backtest.engine.event_source import BacktestEventSource
from app.backtest.engine.metrics import (
    build_round_trips,
    calculate_drawdown,
    calculate_metrics,
    calculate_monthly_returns,
    calculate_risk_metrics,
)
from app.backtest.exchange.mock_exchange import MockExchange
from app.core.constants import DEFAULT_MAKER_FEE, DEFAULT_TAKER_FEE
from app.core.constants import WARMUP as _WARMUP_CONST
from app.core.events import CandleCloseEvent
from app.core.snapshots import ContextSnapshot
from app.trading.engine import Engine
from app.trading.portfolio.manager import PortfolioManager

logger = structlog.get_logger()


class BacktestEngine(Engine):
    """
    Backtest-mode engine.

    Reads a CSV, pre-computes indicators once, then replays candles through
    the unified Engine event loop via BacktestEventSource.

    The key override is _handle_candle_close: before running strategy
    analysis the MockExchange processes the candle's OHLC wicks to check
    for SL/TP fills, mirroring how a real exchange would behave.
    """

    WARMUP = _WARMUP_CONST

    def __init__(self, data_path: str, strategy_class, config: dict) -> None:
        data = pd.read_csv(data_path)

        duration_cfg = config.get("backtest", {}).get("duration", {})
        days = duration_cfg.get("days", 0)
        months = duration_cfg.get("months", 0)
        years = duration_cfg.get("years", 0)
        timeframe = config.get("timeframe", "15m")
        try:
            from app.backtest.data.download import calculate_candle_limit

            limit = calculate_candle_limit(timeframe, days=days, months=months, years=years)
            if limit > 0:
                data = data.tail(limit).reset_index(drop=True)
        except Exception as e:
            logger.warning(f"Could not calculate or apply candle limit: {e}")

        data["timestamp"] = pd.to_datetime(data["timestamp"])

        symbol = config["symbols"][0]
        initial_balance = config.get("backtest", {}).get("initial_balance", 1000.0)
        risk_cfg = config.get("risk", {})
        leverage = risk_cfg.get("leverage", 1)

        taker_fee = float(risk_cfg.get("taker_fee", DEFAULT_TAKER_FEE))
        maker_fee = float(risk_cfg.get("maker_fee", DEFAULT_MAKER_FEE))

        exchange = MockExchange(
            initial_balance=initial_balance,
            leverage=leverage,
            taker_fee=taker_fee,
            maker_fee=maker_fee,
        )
        strategy = strategy_class(config)
        portfolio = PortfolioManager(exchange, config)

        full_df = self._prepare_dataframe(data, strategy, symbol)
        self._full_df = full_df

        event_source = BacktestEventSource(full_df, symbol=symbol, start_idx=self.WARMUP)

        super().__init__(
            event_source=event_source,
            strategy=strategy,
            portfolio=portfolio,
            exchange=exchange,
            symbols=[symbol],
        )

        self.exchange: MockExchange = exchange
        self.symbol = symbol
        self.config = config
        self._initial_balance = float(initial_balance)
        self._on_progress = None
        self._candle_count = 0
        self._last_progress_pct = -1
        self._total_steps = 0

    def _handle_candle_close(self, event: CandleCloseEvent) -> None:
        """Run MockExchange wick-fill checking before strategy analysis."""
        candle = event.candle
        df = event.df
        if df is None:
            return

        row = df.iloc[-1]
        ts = df.index[-1]
        o, h, low, c = float(row["open"]), float(row["high"]), float(row["low"]), float(row["close"])

        executed_orders = self.exchange.update_candle(candle.symbol, o, h, low, c, ts)
        self._sync_executed_orders_to_portfolio(candle.symbol, executed_orders)
        self.portfolio.sync_from_exchange()
        super()._handle_candle_close(event)

        if self._on_progress and self._total_steps > 0:
            pct = min(int(self._candle_count / self._total_steps * 100), 99)
            if pct != self._last_progress_pct and pct % 2 == 0:
                self._on_progress({"pct": pct, "candle": self._candle_count, "total": self._total_steps})
                self._last_progress_pct = pct
        self._candle_count += 1

    def run(self, on_progress=None) -> dict:
        """Run the backtest and return a complete results dict."""
        self._on_progress = on_progress
        self._candle_count = 0
        self._last_progress_pct = -1
        self._total_steps = max(len(self._full_df) - self.WARMUP, 1)

        initial_bal = self.exchange.fetch_balance().get("total", {}).get("USDT", 0)
        default_cfg: dict = getattr(self.strategy, "DEFAULT_CONFIG", {})
        strategy_params = {**default_cfg, **self.config.get("strategy_params", {})}
        logger.info(
            "backtest_start",
            symbol=self.symbol,
            candles=len(self._full_df),
            initial_balance=initial_bal,
            leverage=f"{self.exchange.leverage}x",
            nr_max_above_ema21=strategy_params.get("nr_max_above_ema21", "N/A"),
            nr_rsi_spread_min=strategy_params.get("nr_rsi_spread_min", "N/A"),
        )

        super().run()
        self._close_open_positions()

        if on_progress:
            on_progress({"pct": 100, "candle": self._total_steps, "total": self._total_steps})

        final_bal = self.exchange.fetch_balance().get("total", {}).get("USDT", 0)
        logger.info(
            "backtest_complete",
            final_balance=final_bal,
            open_positions=dict(self.exchange.positions),
            total_trades=len(self.exchange.trade_history),
        )
        return self.compute_results()

    def compute_results(self) -> dict:
        """Compute all performance metrics from exchange trade history."""
        trades = self.exchange.trade_history
        initial = self._initial_balance

        if not trades:
            return {
                "metrics": {},
                "risk_metrics": {
                    "sharpe_ratio": 0,
                    "sortino_ratio": 0,
                    "calmar_ratio": 0,
                    "volatility": 0,
                    "var_95": 0,
                },
                "drawdown": {
                    "max_drawdown_pct": 0,
                    "max_drawdown_value": 0,
                    "max_dd_duration": 0,
                    "avg_drawdown_pct": 0,
                },
                "monthly_returns": {},
                "equity_curve": [],
                "drawdown_curve": [],
                "round_trips": [],
                "initial_balance": initial,
                "final_balance": initial,
                "net_profit": 0.0,
                "net_profit_pct": 0.0,
            }

        df = pd.DataFrame(trades)
        round_trips = build_round_trips(df)
        round_trips_list = round_trips.to_dict(orient="records") if not round_trips.empty else []

        metrics = calculate_metrics(round_trips)
        drawdown_full = calculate_drawdown(round_trips, initial)
        risk_metrics = calculate_risk_metrics(round_trips, drawdown_full, initial)
        monthly_returns = calculate_monthly_returns(round_trips)
        equity_curve = build_equity_curve_dated(round_trips_list, initial)
        drawdown_curve = build_drawdown_curve_dated(equity_curve, initial)

        final_balance = float(self.exchange.fetch_balance().get("total", {}).get("USDT", initial))
        realized_pnl = float(round_trips["pnl"].sum()) if not round_trips.empty else 0.0
        net_profit_pct = (realized_pnl / initial * 100) if initial > 0 else 0.0

        return {
            "metrics": metrics,
            "risk_metrics": risk_metrics,
            "drawdown": {
                "max_drawdown_pct": drawdown_full.get("max_drawdown_pct", 0),
                "max_drawdown_value": drawdown_full.get("max_drawdown_value", 0),
                "max_dd_duration": drawdown_full.get("max_dd_duration", 0),
                "avg_drawdown_pct": drawdown_full.get("avg_drawdown_pct", 0),
            },
            "monthly_returns": monthly_returns,
            "equity_curve": equity_curve,
            "drawdown_curve": drawdown_curve,
            "round_trips": round_trips_list,
            "initial_balance": initial,
            "final_balance": final_balance,
            "net_profit": realized_pnl,
            "net_profit_pct": net_profit_pct,
        }

    @staticmethod
    def _prepare_dataframe(data: pd.DataFrame, strategy, symbol: str) -> pd.DataFrame:
        """Pre-process CSV data and compute all indicators once."""
        df = data.copy()
        df.set_index("timestamp", inplace=True)
        df["closed"] = True
        df["ts"] = df.index.astype(np.int64) // 10**6
        indicators = strategy.indicators
        df = indicators.compute(df, symbol=symbol, timeframe="backtest")
        return df

    def _sync_executed_orders_to_portfolio(self, symbol: str, executed_orders: list) -> None:
        """Sync exchange-executed fills back into PortfolioManager state."""
        for order in executed_orders:
            if order.get("side", "").upper() != "SELL":
                continue

            exit_reason = order.get("info", {}).get("exit_reason", "").upper()
            filled_amount = order.get("filled", order.get("amount", 0))

            if symbol not in self.exchange.positions:
                if symbol in self.portfolio.positions:
                    del self.portfolio.positions[symbol]
                self.contexts[symbol] = ContextSnapshot(state="SCANNING")
                return

            pos = self.portfolio.positions.get(symbol)
            if pos is None:
                continue

            from decimal import Decimal

            filled_dec = Decimal(str(filled_amount))

            if exit_reason in ("TP1", "TP2", "TP3"):
                flag = f"{exit_reason.lower()}_hit"
                setattr(pos, flag, True)
                pos.amount = max(Decimal("0"), pos.amount - filled_dec)
                pos.tp_order_ids.pop(exit_reason, None)
                if exit_reason == "TP1" and pos.amount > Decimal("0"):
                    self.portfolio.move_stop_loss(symbol, pos.entry_price)

    def _close_open_positions(self) -> None:
        """Close all open positions at final price for accurate EOD reporting."""
        if not self.exchange.positions:
            return
        from decimal import Decimal

        last_row = self._full_df.iloc[-1]
        final_price = Decimal(str(last_row["close"]))
        for symbol, amount in list(self.exchange.positions.items()):
            if amount > 0:
                logger.info("closing_eod_position", symbol=symbol, amount=amount, price=final_price)
                self.exchange.create_order(
                    symbol=symbol,
                    order_type="market",
                    side="SELL",
                    amount=Decimal(str(amount)),
                    price=final_price,
                    params={"exit_reason": "EOD"},
                )
