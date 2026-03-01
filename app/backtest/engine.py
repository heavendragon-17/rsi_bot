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

from app.core.engine import Engine
from app.core.events import CandleCloseEvent
from app.core.snapshots import ContextSnapshot
from app.backtest.backtest_event_source import BacktestEventSource
from app.backtest.mock_exchange import MockExchange
from app.core.portfolio import PortfolioManager

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

    # Number of warm-up candles skipped before strategy analysis begins.
    WARMUP = 220

    def __init__(self, data_path: str, strategy_class, config: dict) -> None:
        data = pd.read_csv(data_path)
        data["timestamp"] = pd.to_datetime(data["timestamp"])

        symbol = config["symbols"][0]
        initial_balance = config.get("backtest", {}).get("initial_balance", 1000.0)
        risk_cfg = config.get("risk", {})
        leverage = risk_cfg.get("leverage", 1)

        # Use same default fees as SimExchange (Binance futures)
        taker_fee = float(risk_cfg.get("taker_fee", 0.0005))   # 0.05%
        maker_fee = float(risk_cfg.get("maker_fee", 0.0002))   # 0.02%

        exchange = MockExchange(
            initial_balance=initial_balance,
            leverage=leverage,
            taker_fee=taker_fee,
            maker_fee=maker_fee,
        )
        strategy = strategy_class(config)
        portfolio = PortfolioManager(exchange, config)

        # Pre-compute all indicators ONCE across the full dataset
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

        self.symbol = symbol
        self.config = config
        self._initial_balance = float(initial_balance)

        # Progress tracking — initialised to safe defaults, set in run()
        self._on_progress = None
        self._candle_count = 0
        self._last_progress_pct = -1
        self._total_steps = 0

    # ------------------------------------------------------------------
    # BacktestEngine-specific override
    # ------------------------------------------------------------------

    def _handle_candle_close(self, event: CandleCloseEvent) -> None:
        """
        Run MockExchange wick-fill checking before strategy analysis,
        then report progress to the caller.
        """
        candle = event.candle
        df = event.df

        if df is None:
            return

        row = df.iloc[-1]
        ts = df.index[-1]
        o = float(row["open"])
        h = float(row["high"])
        l = float(row["low"])
        c = float(row["close"])

        # Let MockExchange check wicks against pending SL/TP orders
        executed_orders = self.exchange.update_candle(candle.symbol, o, h, l, c, ts)

        # Sync exchange-executed orders back into portfolio state.
        # This covers two cases:
        #  1. PARTIAL TP fill (limit order fired by update_candle): mark tp1/2/3_hit
        #     and reduce pos.amount so strategy.analyze() won't emit a duplicate
        #     PartialClose on the same candle (which would sell at close price instead
        #     of the exact TP price, producing variable and incorrect PnL).
        #  2. Full position close (SL or final TP): clear portfolio position and
        #     reset context to SCANNING so new entries can fire immediately.
        self._sync_executed_orders_to_portfolio(candle.symbol, executed_orders)

        self.portfolio.sync_from_exchange()

        # Now run the normal strategy analysis + action dispatch
        super()._handle_candle_close(event)

        # Progress callback — fire every 2% of total steps
        if self._on_progress and self._total_steps > 0:
            pct = int(self._candle_count / self._total_steps * 100)
            pct = min(pct, 99)  # 100 is sent by run() on completion
            if pct != self._last_progress_pct and pct % 2 == 0:
                self._on_progress({
                    "pct": pct,
                    "candle": self._candle_count,
                    "total": self._total_steps,
                })
                self._last_progress_pct = pct

        self._candle_count += 1

    # ------------------------------------------------------------------
    # Entry point
    # ------------------------------------------------------------------

    def run(self, on_progress=None) -> dict:
        """
        Run the backtest and return a complete results dict.

        Parameters
        ----------
        on_progress : callable | None
            Called with ``{"pct": int, "candle": int, "total": int}`` every 2%.
            Receives ``{"pct": 100, ...}`` once at completion.
        """
        self._on_progress = on_progress
        self._candle_count = 0
        self._last_progress_pct = -1
        self._total_steps = max(len(self._full_df) - self.WARMUP, 1)

        initial_bal = self.exchange.fetch_balance().get("total", {}).get("USDT", 0)
        logger.info(
            "backtest_start",
            symbol=self.symbol,
            candles=len(self._full_df),
            initial_balance=initial_bal,
            leverage=f"{self.exchange.leverage}x",
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

    # ------------------------------------------------------------------
    # Results computation
    # ------------------------------------------------------------------

    def compute_results(self) -> dict:
        """
        Compute all performance metrics from exchange trade history.

        Returns the canonical results dict consumed by BacktestReporter
        and stored in the DB (Phase 3+).
        """
        trades = self.exchange.trade_history
        initial = self._initial_balance

        if not trades:
            return {
                "metrics": {},
                "risk_metrics": {
                    "sharpe_ratio": 0, "sortino_ratio": 0,
                    "calmar_ratio": 0, "volatility": 0, "var_95": 0,
                },
                "drawdown": {
                    "max_drawdown_pct": 0, "max_drawdown_value": 0,
                    "max_dd_duration": 0, "avg_drawdown_pct": 0,
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
        round_trips = self._build_round_trips(df)
        round_trips_list = (
            round_trips.to_dict(orient="records") if not round_trips.empty else []
        )

        metrics = self._calculate_metrics(round_trips)
        drawdown_full = self._calculate_drawdown(round_trips, initial)
        risk_metrics = self._calculate_risk_metrics(round_trips, drawdown_full, initial)
        monthly_returns = self._calculate_monthly_returns(round_trips)

        equity_curve = self._build_equity_curve_dated(round_trips_list, initial)
        drawdown_curve = self._build_drawdown_curve_dated(equity_curve, initial)

        final_balance = float(
            self.exchange.fetch_balance().get("total", {}).get("USDT", initial)
        )
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

    # ------------------------------------------------------------------
    # Computation helpers (static — no instance state needed)
    # ------------------------------------------------------------------

    @staticmethod
    def _build_round_trips(trades_df: pd.DataFrame) -> pd.DataFrame:
        """Pair BUY entries with SELL exits to form complete round-trips."""
        if trades_df.empty:
            return pd.DataFrame()

        round_trips = []
        current_entry = None
        partial_exits = []
        total_pnl = 0.0
        total_exit_amount = 0.0

        for _, trade in trades_df.iterrows():
            if trade["side"] == "BUY":
                if current_entry is not None and partial_exits:
                    round_trips.append(BacktestEngine._create_round_trip(
                        current_entry, partial_exits, total_pnl, total_exit_amount
                    ))
                current_entry = trade
                partial_exits = []
                total_pnl = 0.0
                total_exit_amount = 0.0
            elif trade["side"] == "SELL" and current_entry is not None:
                partial_exits.append(trade)
                if trade["pnl"] is not None:
                    total_pnl += trade["pnl"]
                total_exit_amount += trade["amount"]

        if current_entry is not None and partial_exits:
            round_trips.append(BacktestEngine._create_round_trip(
                current_entry, partial_exits, total_pnl, total_exit_amount
            ))

        return pd.DataFrame(round_trips) if round_trips else pd.DataFrame()

    @staticmethod
    def _create_round_trip(entry, exits, total_pnl, total_exit_amount) -> dict:
        last_exit = exits[-1]

        def get_exit_reason(e):
            return e.get("info", {}).get("exit_reason") or ""

        exit_reasons = [get_exit_reason(e) for e in exits if get_exit_reason(e)]
        final_exit_reason = BacktestEngine._get_highest_exit_reason(exit_reasons)

        hold_duration_seconds = None
        if entry.get("time") is not None and last_exit.get("time") is not None:
            try:
                entry_time = pd.to_datetime(entry["time"])
                exit_time = pd.to_datetime(last_exit["time"])
                hold_duration_seconds = (exit_time - entry_time).total_seconds()
            except Exception:
                pass

        total_revenue = sum(e.get("price", 0) * e.get("amount", 0) for e in exits)
        avg_exit_price = total_revenue / total_exit_amount if total_exit_amount > 0 else 0

        entry_margin = entry.get("margin", entry.get("notional", 1))
        entry_notional = entry.get("notional", entry_margin)
        pnl_pct = (total_pnl / entry_margin) * 100 if entry_margin and entry_margin > 0 else 0

        return {
            "entry_time": entry.get("time"),
            "exit_time": last_exit.get("time"),
            "symbol": entry.get("symbol"),
            "entry_price": entry.get("price"),
            "exit_price": last_exit.get("price"),
            "avg_exit_price": float(avg_exit_price),
            "amount": entry.get("amount"),
            "exit_amount": total_exit_amount,
            "margin": entry_margin,
            "notional": entry_notional,
            "leverage": entry.get("leverage", 1),
            "pnl": total_pnl,
            "pnl_pct": pnl_pct,
            "hold_duration_seconds": hold_duration_seconds,
            "hold_duration_hours": (
                hold_duration_seconds / 3600 if hold_duration_seconds else None
            ),
            "exit_reason": final_exit_reason,
            "num_partial_exits": len(exits),
            "hit_tp1": any(get_exit_reason(e) == "TP1" for e in exits),
            "hit_tp2": any(get_exit_reason(e) == "TP2" for e in exits),
            "hit_tp3": any(get_exit_reason(e) == "TP3" for e in exits),
            "hit_sl": any(get_exit_reason(e) in ("SL", "STOP_LOSS") for e in exits),
        }

    @staticmethod
    def _get_highest_exit_reason(exit_reasons: list) -> str:
        if any(r in ("SL", "STOP_LOSS") for r in exit_reasons):
            has_tp = any(r and r.startswith("TP") for r in exit_reasons)
            if has_tp:
                for tp in ["TP3", "TP2", "TP1"]:
                    if tp in exit_reasons:
                        return f"{tp}+SL"
            return "SL"
        for tp in ["TP3", "TP2", "TP1"]:
            if tp in exit_reasons:
                return tp
        return exit_reasons[0] if exit_reasons else "UNKNOWN"

    @staticmethod
    def _calculate_metrics(round_trips: pd.DataFrame) -> dict:
        if round_trips.empty:
            return {}

        total_trades = len(round_trips)
        wins = round_trips[round_trips["pnl"] > 0]
        losses = round_trips[round_trips["pnl"] <= 0]
        win_count = len(wins)
        loss_count = len(losses)
        win_rate = (win_count / total_trades * 100) if total_trades > 0 else 0

        total_pnl = round_trips["pnl"].sum()
        avg_pnl = round_trips["pnl"].mean()
        avg_win = wins["pnl"].mean() if len(wins) > 0 else 0
        avg_loss = losses["pnl"].mean() if len(losses) > 0 else 0
        largest_win = round_trips["pnl"].max()
        largest_loss = round_trips["pnl"].min()

        gross_profit = wins["pnl"].sum() if len(wins) > 0 else 0
        gross_loss = abs(losses["pnl"].sum()) if len(losses) > 0 else 0
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else float("inf")
        risk_reward = abs(avg_win / avg_loss) if avg_loss != 0 else float("inf")
        expectancy = (win_rate / 100 * avg_win) + ((1 - win_rate / 100) * avg_loss)

        hold_hours = round_trips["hold_duration_hours"].dropna()
        avg_hold_hours = hold_hours.mean() if len(hold_hours) > 0 else 0

        tp1_count = int(round_trips["hit_tp1"].sum())
        tp2_count = int(round_trips["hit_tp2"].sum())
        tp3_count = int(round_trips["hit_tp3"].sum())
        sl_count = int(round_trips["hit_sl"].sum())
        exit_reason_counts = round_trips["exit_reason"].value_counts().to_dict()

        pnl_signs = (round_trips["pnl"] > 0).astype(int)
        max_consec_wins = BacktestEngine._max_consecutive(pnl_signs, 1)
        max_consec_losses = BacktestEngine._max_consecutive(pnl_signs, 0)

        return {
            "total_trades": total_trades,
            "win_count": win_count,
            "loss_count": loss_count,
            "win_rate": win_rate,
            "total_pnl": float(total_pnl),
            "avg_pnl": float(avg_pnl),
            "avg_win": float(avg_win),
            "avg_loss": float(avg_loss),
            "largest_win": float(largest_win),
            "largest_loss": float(largest_loss),
            "profit_factor": profit_factor,
            "risk_reward": risk_reward,
            "expectancy": float(expectancy),
            "avg_hold_hours": float(avg_hold_hours),
            "tp1_count": tp1_count,
            "tp2_count": tp2_count,
            "tp3_count": tp3_count,
            "sl_count": sl_count,
            "exit_reason_counts": exit_reason_counts,
            "max_consec_wins": max_consec_wins,
            "max_consec_losses": max_consec_losses,
            "gross_profit": float(gross_profit),
            "gross_loss": float(gross_loss),
        }

    @staticmethod
    def _max_consecutive(series, value) -> int:
        max_count = 0
        current = 0
        for v in series:
            if v == value:
                current += 1
                max_count = max(max_count, current)
            else:
                current = 0
        return max_count

    @staticmethod
    def _calculate_drawdown(round_trips: pd.DataFrame, initial_balance: float) -> dict:
        if round_trips.empty or "pnl" not in round_trips.columns:
            return {
                "max_drawdown_pct": 0, "max_drawdown_value": 0,
                "equity_curve": [float(initial_balance)],
                "max_dd_duration": 0, "avg_drawdown_pct": 0,
            }

        cumulative_pnl = round_trips["pnl"].cumsum().tolist()
        equity_curve = [initial_balance] + [initial_balance + p for p in cumulative_pnl]

        peak = equity_curve[0]
        max_dd = max_dd_value = 0.0
        max_dd_duration = current_dd_duration = 0
        all_drawdowns = []

        for val in equity_curve:
            if val > peak:
                peak = val
                if current_dd_duration > 0:
                    max_dd_duration = max(max_dd_duration, current_dd_duration)
                current_dd_duration = 0
            else:
                dd = (peak - val) / peak if peak > 0 else 0
                if dd > 0:
                    all_drawdowns.append(dd * 100)
                    current_dd_duration += 1
                if dd > max_dd:
                    max_dd = dd
                    max_dd_value = peak - val

        if current_dd_duration > 0:
            max_dd_duration = max(max_dd_duration, current_dd_duration)

        avg_drawdown = sum(all_drawdowns) / len(all_drawdowns) if all_drawdowns else 0

        return {
            "max_drawdown_pct": max_dd * 100,
            "max_drawdown_value": max_dd_value,
            "equity_curve": equity_curve,   # plain floats — internal use only
            "max_dd_duration": max_dd_duration,
            "avg_drawdown_pct": avg_drawdown,
        }

    @staticmethod
    def _calculate_risk_metrics(
        round_trips: pd.DataFrame, drawdown: dict, initial_balance: float
    ) -> dict:
        zero = {"sharpe_ratio": 0, "sortino_ratio": 0, "calmar_ratio": 0,
                "volatility": 0, "var_95": 0}
        if round_trips.empty:
            return zero

        returns = round_trips["pnl_pct"].values / 100
        if len(returns) < 2:
            return zero

        mean_return = np.mean(returns)
        std_return = np.std(returns, ddof=1)
        volatility = std_return * 100
        sharpe_ratio = mean_return / std_return if std_return > 0 else 0

        negative_returns = returns[returns < 0]
        downside_std = np.std(negative_returns, ddof=1) if len(negative_returns) > 1 else 0
        sortino_ratio = mean_return / downside_std if downside_std > 0 else 0

        var_95 = (
            np.percentile(returns, 5) * 100
            if len(returns) >= 5
            else min(returns) * 100
        )

        realized_pnl = float(round_trips["pnl"].sum())
        total_return = (realized_pnl / initial_balance) * 100 if initial_balance > 0 else 0
        max_dd = drawdown.get("max_drawdown_pct", 0)
        calmar_ratio = total_return / max_dd if max_dd > 0 else 0

        return {
            "sharpe_ratio": sharpe_ratio,
            "sortino_ratio": sortino_ratio,
            "calmar_ratio": calmar_ratio,
            "volatility": volatility,
            "var_95": var_95,
        }

    @staticmethod
    def _calculate_monthly_returns(round_trips: pd.DataFrame) -> dict:
        if round_trips.empty or "exit_time" not in round_trips.columns:
            return {}

        df = round_trips.copy()
        df["exit_time"] = pd.to_datetime(df["exit_time"])
        df["month"] = df["exit_time"].dt.to_period("M")

        monthly = df.groupby("month").agg(pnl=("pnl", "sum"), trades=("pnl", "count"))

        return {
            str(period): {
                "pnl": float(row["pnl"]),
                "pnl_pct": 0.0,
                "trades": int(row["trades"]),
            }
            for period, row in monthly.iterrows()
        }

    @staticmethod
    def _build_equity_curve_dated(round_trips_list: list, initial_balance: float) -> list:
        """Build ``[{date, balance}]`` annotated with each trade's exit timestamp."""
        curve = []
        balance = initial_balance
        for rt in round_trips_list:
            balance += rt.get("pnl") or 0
            exit_time = rt.get("exit_time")
            if hasattr(exit_time, "isoformat"):
                date_str = exit_time.isoformat()
            else:
                date_str = str(exit_time) if exit_time is not None else ""
            curve.append({"date": date_str, "balance": round(balance, 2)})
        return curve

    @staticmethod
    def _build_drawdown_curve_dated(equity_curve: list, initial_balance: float) -> list:
        """Build ``[{date, drawdown}]`` from the dated equity curve."""
        peak = initial_balance
        curve = []
        for point in equity_curve:
            balance = point["balance"]
            if balance > peak:
                peak = balance
            dd_pct = (peak - balance) / peak * 100 if peak > 0 else 0.0
            curve.append({"date": point["date"], "drawdown": round(dd_pct, 4)})
        return curve

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _prepare_dataframe(data: pd.DataFrame, strategy, symbol: str) -> pd.DataFrame:
        """Pre-process CSV data and compute all indicators once."""
        df = data.copy()
        df.set_index("timestamp", inplace=True)
        df["closed"] = True
        df["ts"] = df.index.astype(np.int64) // 10 ** 6

        indicators = strategy.indicators
        df = indicators.compute(df, symbol=symbol, timeframe="backtest")
        return df

    def _sync_executed_orders_to_portfolio(self, symbol: str, executed_orders: list) -> None:
        """
        After update_candle() fires pending limit/stop orders, sync the fills back
        into PortfolioManager so the strategy sees the correct state on the same candle.

        Without this, strategy.analyze() reads position.tp1_hit=False and emits a
        PartialClose on the same candle that already had its TP1 limit order fill,
        causing a second sell at the candle's close price (variable PnL) instead of
        the precise TP1 price we computed.

        Two outcomes handled:
        - Partial TP fill: mark tp_hit flag, reduce pos.amount on the position record.
        - Full close (SL or final TP): remove portfolio position, reset context to SCANNING.
        """
        for order in executed_orders:
            if order.get("side", "").upper() != "SELL":
                continue

            exit_reason = order.get("info", {}).get("exit_reason", "").upper()
            filled_amount = order.get("filled", order.get("amount", 0))

            # --- Full close: clear portfolio position and reset strategy context ---
            if symbol not in self.exchange.positions:
                if symbol in self.portfolio.positions:
                    del self.portfolio.positions[symbol]
                self.contexts[symbol] = ContextSnapshot(state="SCANNING")
                return  # position gone — nothing more to sync

            # --- Partial TP fill: update portfolio position state ---
            pos = self.portfolio.positions.get(symbol)
            if pos is None:
                continue

            from decimal import Decimal
            filled_dec = Decimal(str(filled_amount))

            if exit_reason in ("TP1", "TP2", "TP3"):
                # Mark the TP level hit so strategy.analyze() won't emit PartialClose
                flag = f"{exit_reason.lower()}_hit"
                setattr(pos, flag, True)
                # Reduce portfolio pos.amount to match exchange position
                pos.amount = max(Decimal("0"), pos.amount - filled_dec)
                # Remove the TP order id so execute_partial_close cancel doesn't fail
                pos.tp_order_ids.pop(exit_reason, None)

    def _close_open_positions(self) -> None:
        """Close all open positions at final price for accurate EOD reporting."""
        if not self.exchange.positions:
            return

        last_row = self._full_df.iloc[-1]
        final_price = float(last_row["close"])

        for symbol, amount in list(self.exchange.positions.items()):
            if amount > 0:
                logger.info(
                    "closing_eod_position",
                    symbol=symbol,
                    amount=amount,
                    price=final_price,
                )
                self.exchange.create_order(
                    symbol=symbol,
                    order_type="market",
                    side="SELL",
                    amount=float(amount),
                    price=final_price,
                    params={"exit_reason": "EOD"},
                )
