"""Risk-based position sizing logic."""

from __future__ import annotations

from decimal import Decimal
from typing import Optional

import structlog

from app.core.interfaces import IExchange
from app.core.utils import to_decimal

logger = structlog.get_logger()


class PositionSizer:
    """Calculates position size based on risk parameters and leverage."""

    def __init__(self, config: dict, exchange: IExchange):
        self.exchange = exchange

        risk_cfg = config.get("risk", {})
        self.max_position_size_pct = Decimal(str(risk_cfg.get("max_position_size_pct", 0.99)))
        self.risk_per_trade_pct = Decimal(str(risk_cfg.get("risk_per_trade_pct", 0.02)))
        self.use_risk_based_sizing = bool(risk_cfg.get("use_risk_based_sizing", True))
        self.min_sl_distance_pct = Decimal(str(risk_cfg.get("min_sl_distance_pct", 0.01)))
        self.leverage = Decimal(str(risk_cfg.get("leverage", 1)))
        self.use_initial_capital_for_risk = bool(risk_cfg.get("use_initial_capital_for_risk", True))

        backtest_cfg = config.get("backtest", {})
        self.initial_capital = Decimal(str(backtest_cfg.get("initial_balance", 10000)))

    def sync_balance(self) -> Decimal:
        bal = self.exchange.fetch_balance()
        return to_decimal(bal.get("total", {}).get("USDT", 0))

    def calculate(
        self, balance: Decimal, entry_price: Decimal, sl_price: Optional[Decimal]
    ) -> Decimal:
        """
        Calculate position size for futures trading with leverage.

        Risk-Based Formula (Futures):
            risk_capital = initial_capital (or current balance)
            risk_amount = risk_capital * risk_per_trade_pct
            sl_distance_pct = |entry_price - sl_price| / entry_price
            position_notional = risk_amount / sl_distance_pct
            position_size = position_notional / entry_price
            margin_required = position_notional / leverage
        """
        if self.use_initial_capital_for_risk:
            risk_capital = self.initial_capital
            cap_balance = self.initial_capital
        else:
            risk_capital = balance
            cap_balance = balance

        max_margin = cap_balance * self.max_position_size_pct
        max_notional = max_margin * self.leverage
        max_amount = max_notional / entry_price

        if self.use_risk_based_sizing and sl_price is not None and sl_price > Decimal("0"):
            sl_distance = abs(entry_price - sl_price)
            sl_distance_pct = sl_distance / entry_price if entry_price > Decimal("0") else Decimal("0")

            if sl_distance_pct <= Decimal("0"):
                logger.error(f"SL distance is zero (SL={sl_price}, Entry={entry_price}). Cannot calculate position size.")
                return Decimal("0")

            if sl_distance_pct < self.min_sl_distance_pct:
                risk_amount = risk_capital * self.risk_per_trade_pct
                position_notional = risk_amount / sl_distance_pct
                position_size = position_notional / entry_price
                capped_size = min(position_size, max_amount)
                logger.warning(
                    f"SL distance too small ({sl_distance_pct*100:.2f}% < {self.min_sl_distance_pct*100:.0f}%). "
                    f"Risk-based size={position_size:.4f}, capped to {capped_size:.4f}"
                )
                return capped_size

            if sl_distance_pct > Decimal("0"):
                risk_amount = risk_capital * self.risk_per_trade_pct
                position_notional = risk_amount / sl_distance_pct
                position_size = position_notional / entry_price
                margin_required = position_notional / self.leverage

                final_size = min(position_size, max_amount)
                was_capped = position_size > max_amount

                logger.info(
                    f"[SIZING] Entry=${entry_price:.4f}, SL=${sl_price:.4f}, "
                    f"Dist={sl_distance_pct*100:.2f}%, Risk=${risk_amount:.2f}, "
                    f"Notional=${position_notional:.2f}, Size={final_size:.6f}"
                )

                if was_capped:
                    actual_notional = final_size * entry_price
                    actual_risk = actual_notional * sl_distance_pct
                    logger.info(
                        f"[CAPPED] Position capped! Target risk: ${risk_amount:.2f}, "
                        f"Actual risk: ${actual_risk:.2f} ({(actual_risk/risk_capital)*100:.2f}%)"
                    )

                return final_size

        return max_amount
