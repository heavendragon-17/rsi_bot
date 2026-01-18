import os
import pandas as pd
import threading
from decimal import Decimal
from typing import Any, Dict, List, Optional
from dataclasses import dataclass
from pathlib import Path

import ccxt
from binance.um_futures import UMFutures

from app.core.interfaces import IFuturesExchange

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    env_path = Path(__file__).parent.parent.parent.parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)
    else:
        load_dotenv()
except ImportError:
    pass


def to_decimal(val) -> Decimal:
    if val is None:
        return Decimal("0")
    if isinstance(val, Decimal):
        return val
    return Decimal(str(val))


def _to_external_symbol(symbol: str) -> str:
    """
    Normalize to CCXT futures style: BTC/USDT:USDT
    Accepts:
      - BTC/USDT:USDT
      - BTC/USDT
      - BTCUSDT
    """
    s = (symbol or "").strip().upper()
    if not s:
        return s

    if "/" in s and ":" in s:
        return s

    if "/" in s and ":" not in s:
        return f"{s}:USDT"

    if s.endswith("USDT") and "/" not in s:
        base = s[:-4]
        return f"{base}/USDT:USDT"

    return s


def _to_um_symbol(symbol: str) -> str:
    """
    Convert external (ccxt-style) to UMFutures symbol: BTCUSDT
    """
    s = (symbol or "").strip().upper()
    if not s:
        return s

    if ":" in s:
        s = s.split(":", 1)[0]

    if "/" in s:
        base, quote = s.split("/", 1)
        return f"{base}{quote}"

    return s


class UMFuturesPaperClient:
    """
    CCXT-ish wrapper around UMFutures for PAPER mode.
    Only implements what your tests call:
      - fetch_ticker(symbol) -> {'last': float, 'symbol': <external symbol>}
      - fetch_ohlcv(symbol, timeframe, limit) -> [[ts, o,h,l,c,v], ...]
    """

    def __init__(self, um: UMFutures):
        self.um = um

    def fetch_ticker(self, symbol: str) -> Dict[str, Any]:
        ext = _to_external_symbol(symbol)
        um_sym = _to_um_symbol(ext)
        # UM returns: {'symbol': 'BTCUSDT', 'price': '...'}
        t = self.um.ticker_price(symbol=um_sym)
        last = float(t["price"])
        return {
            "symbol": ext,
            "last": last,
            "info": t,
        }

    def fetch_ohlcv(self, symbol: str, timeframe: str, limit: int = 500) -> List[List[Any]]:
        ext = _to_external_symbol(symbol)
        um_sym = _to_um_symbol(ext)

        tf_map = {
            "1m": "1m", "3m": "3m", "5m": "5m", "15m": "15m", "30m": "30m",
            "1h": "1h", "2h": "2h", "4h": "4h", "6h": "6h", "8h": "8h", "12h": "12h",
            "1d": "1d", "1w": "1w",
        }
        interval = tf_map.get(timeframe, timeframe)

        data = self.um.klines(symbol=um_sym, interval=interval, limit=limit)
        out: List[List[Any]] = []
        for k in data:
            out.append([k[0], float(k[1]), float(k[2]), float(k[3]), float(k[4]), float(k[5])])
        return out


@dataclass
class Position:
    symbol: str
    amount: Decimal
    entry_price: Decimal
    entry_time: Any
    margin_used: Decimal


class BinanceAdapter(IFuturesExchange):
    """
    PAPER mode:
      - adapter.client is UMFuturesPaperClient (has fetch_ticker/fetch_ohlcv like CCXT)
      - orders are simulated locally (your existing _execute_order logic)
      - market data uses UMFutures demo-fapi

    LIVE mode:
      - adapter.client is ccxt.binanceusdm (real trading)

    IMPORTANT: all simulation dictionaries are keyed by CCXT-style symbol: BTC/USDT:USDT
    """

    def __init__(
        self,
        config: dict = None,
        initial_balance: float = 1000.0,
        leverage: int = 1,
        maker_fee: float = 0.0,
        taker_fee: float = 0.0,
        env_file: Optional[str] = None,
    ):
        if env_file:
            try:
                from dotenv import load_dotenv
                load_dotenv(env_file)
            except ImportError:
                print("Warning: python-dotenv not installed. Install with: pip install python-dotenv")

        self.config = config or {}
        bot_cfg = self.config.get("bot", {})
        self.mode = (bot_cfg.get("mode") or "paper").lower()
        if self.mode not in ("paper", "live"):
            self.mode = "paper"

        self._lock = threading.RLock()

        # Simulated account state
        self.balance = to_decimal(initial_balance)
        self.leverage = Decimal(str(leverage))
        self.maker_fee = Decimal(str(maker_fee))
        self.taker_fee = Decimal(str(taker_fee))

        # Simulation bookkeeping (CCXT-style keys)
        self.positions: Dict[str, Decimal] = {}
        self.margin_used: Dict[str, Decimal] = {}
        self.entry_times: Dict[str, Any] = {}
        self.entry_prices: Dict[str, Decimal] = {}
        self.trade_history: List[Dict] = []
        self.current_prices: Dict[str, Dict] = {}
        self.pending_orders: Dict[str, Dict] = {}
        self._order_counter = 0

        # Init clients
        if self.mode == "paper":
            self._um = self._init_um_demo_client()
            self.client = UMFuturesPaperClient(self._um)  # <- tests call adapter.client.fetch_ticker
        else:
            self._ccxt = self._init_ccxt_live_client()
            self.client = self._ccxt  # <- live uses ccxt

    # ---------- client init ----------

    def _get_api_credentials(self, mode: str) -> tuple[str, str]:
        mode = (mode or "").lower()
        if mode == "paper":
            api_key = os.getenv("BINANCE_TESTNET_API_KEY") or os.getenv("BINANCE_API_KEY")
            secret = os.getenv("BINANCE_TESTNET_SECRET_KEY") or os.getenv("BINANCE_SECRET_KEY")
        else:
            api_key = os.getenv("BINANCE_API_KEY")
            secret = os.getenv("BINANCE_SECRET_KEY")

        if not api_key or not secret:
            raise RuntimeError("Missing BINANCE_API_KEY / BINANCE_SECRET_KEY environment variables")

        return api_key, secret

    def _init_um_demo_client(self) -> UMFutures:
        api_key, secret = self._get_api_credentials("paper")
        return UMFutures(
            key=api_key,
            secret=secret,
            base_url="https://demo-fapi.binance.com",
        )

    def _init_ccxt_live_client(self) -> ccxt.binanceusdm:
        api_key, secret = self._get_api_credentials("live")
        client = ccxt.binanceusdm({
            "apiKey": api_key,
            "secret": secret,
            "enableRateLimit": True,
            "options": {"defaultType": "future"},
        })
        client.load_markets()
        return client

    # ---------- helpers ----------

    def _to_float(self, val: Optional[Decimal]) -> Optional[float]:
        if val is None:
            return None
        return float(val) if isinstance(val, Decimal) else float(Decimal(str(val)))

    def _next_order_id(self) -> str:
        self._order_counter += 1
        return f"mock_order_{self._order_counter}"

    # ========== Account Information ==========

    def fetch_balance(self) -> Dict[str, Any]:
        with self._lock:
            if self.mode == "live":
                try:
                    return self.client.fetch_balance()
                except Exception as e:
                    print(f"BinanceAdapter.fetch_balance failed: {e}")
                    return {}

            # paper simulation
            total_margin_used = sum(self.margin_used.values())
            free_balance = self.balance
            return {
                "USDT": {
                    "free": float(free_balance),
                    "used": float(total_margin_used),
                    "total": float(free_balance + total_margin_used),
                },
                "free": {"USDT": float(free_balance)},
                "used": {"USDT": float(total_margin_used)},
                "total": {"USDT": float(free_balance + total_margin_used)},
            }

    # ========== Market Data Methods ==========

    def fetch_ohlcv(self, symbol: str, timeframe: str, limit: int) -> List[List[Any]]:
        # paper uses UM wrapper, live uses ccxt directly; both expose fetch_ohlcv signature
        ext = _to_external_symbol(symbol)
        return self.client.fetch_ohlcv(ext, timeframe, limit=limit)

    def fetch_candles_df_multi(self, symbols: List[str], timeframe: str, limit: int = 500) -> Dict[str, pd.DataFrame]:
        result: Dict[str, pd.DataFrame] = {}
        for symbol in symbols:
            ext = _to_external_symbol(symbol)
            raw = self.fetch_ohlcv(ext, timeframe, limit)
            df = pd.DataFrame(raw, columns=["timestamp", "open", "high", "low", "close", "volume"])
            df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
            df = df.set_index("timestamp")
            result[ext] = df
        return result

    # ========== Position Management ==========

    def fetch_positions(self, symbols: Optional[List[str]] = None) -> List[Dict]:
        with self._lock:
            if self.mode == "live":
                try:
                    ext_symbols = [_to_external_symbol(s) for s in symbols] if symbols else None
                    positions = self.client.fetch_positions(ext_symbols)
                    return [p for p in positions if p.get("contracts", 0) != 0]
                except Exception as e:
                    print(f"BinanceAdapter.fetch_positions failed: {e}")
                    return []

            # paper simulation
            wanted = {_to_external_symbol(s) for s in symbols} if symbols else None
            pos_list: List[Dict] = []

            for sym, amt in self.positions.items():
                if wanted and sym not in wanted:
                    continue
                amt_dec = to_decimal(amt)
                if amt_dec == 0:
                    continue

                entry = self.entry_prices.get(sym, Decimal("0"))
                curr_data = self.current_prices.get(sym)
                if curr_data and "price" in curr_data:
                    curr = to_decimal(curr_data["price"])
                else:
                    # fetch real-ish last price from UM via wrapper
                    curr = to_decimal(self.client.fetch_ticker(sym)["last"])

                upnl = (curr - entry) * amt_dec if amt_dec > 0 else (entry - curr) * abs(amt_dec)

                pos_list.append({
                    "symbol": sym,
                    "contracts": float(abs(amt_dec)),
                    "contractSize": 1.0,
                    "unrealizedPnl": float(upnl),
                    "leverage": float(self.leverage),
                    "entryPrice": float(entry),
                    "side": "long" if amt_dec > 0 else "short",
                    "notional": float(abs(amt_dec) * curr),
                    "markPrice": float(curr),
                    "info": {"positionAmt": float(amt_dec)},
                })

            return pos_list

    def set_leverage(self, symbol: str, leverage: int) -> bool:
        ext = _to_external_symbol(symbol)
        try:
            with self._lock:
                if self.mode == "live":
                    self.client.set_leverage(leverage, ext)
                self.leverage = Decimal(str(leverage))
                return True
        except Exception as e:
            print(f"BinanceAdapter.set_leverage failed: symbol={ext}, leverage={leverage}, err={e}")
            return False

    # ========== Order Management ==========

    def create_order(
        self,
        symbol: str,
        order_type: str,
        side: str,
        amount: Decimal,
        price: Optional[Decimal] = None
    ) -> Dict:
        ext = _to_external_symbol(symbol)
        order_type_l = (order_type or "").strip().lower()
        side_l = (side or "").strip().lower()

        if self.mode == "live":
            amt = self._to_float(amount)
            prc = self._to_float(price)
            return self.client.create_order(ext, order_type_l, side_l, amt, prc, {})

        # paper -> simulate using real prices from UM wrapper
        try:
            last = to_decimal(self.client.fetch_ticker(ext)["last"])
        except Exception:
            last = price if price is not None else Decimal("50000")

        exec_price = last if order_type_l == "market" else (price if price is not None else last)

        from datetime import datetime
        return self._execute_order(
            symbol=ext,
            side=side_l,
            amount=amount,
            price=exec_price,
            order_type=order_type_l,
            timestamp=datetime.now()
        )

    def cancel_order(self, order_id: str, symbol: str) -> bool:
        ext = _to_external_symbol(symbol)
        try:
            if self.mode == "live":
                self.client.cancel_order(order_id, ext)
                return True
            self.pending_orders.pop(order_id, None)
            return True
        except Exception as e:
            print(f"BinanceAdapter.cancel_order failed: order_id={order_id}, symbol={ext}, err={e}")
            return False

    def cancel_orders_for_symbol(self, symbol: str) -> bool:
        ext = _to_external_symbol(symbol)
        try:
            if self.mode == "live":
                open_orders = self.client.fetch_open_orders(ext)
                ok = True
                for o in open_orders:
                    try:
                        self.client.cancel_order(o["id"], ext)
                    except Exception as e:
                        print(f"Failed to cancel {o.get('id')}: {e}")
                        ok = False
                return ok

            # paper
            to_delete = [oid for oid, o in self.pending_orders.items() if o.get("symbol") == ext]
            for oid in to_delete:
                self.pending_orders.pop(oid, None)
            return True
        except Exception as e:
            print(f"BinanceAdapter.cancel_orders_for_symbol failed: symbol={ext}, err={e}")
            return False

    # ========== Stop Loss / Take Profit (simulation placeholders) ==========

    def place_stop_loss(self, symbol: str, side: str, amount: Decimal, stop_price: Decimal) -> Optional[Dict]:
        ext = _to_external_symbol(symbol)
        try:
            oid = self._next_order_id()
            self.pending_orders[oid] = {
                "id": oid,
                "symbol": ext,
                "type": "stop_market",
                "side": side.lower(),
                "amount": float(amount),
                "stopPrice": float(stop_price),
                "status": "open",
            }
            return self.pending_orders[oid]
        except Exception as e:
            print(f"BinanceAdapter.place_stop_loss failed: symbol={ext}, err={e}")
            return None

    def place_take_profit(self, symbol: str, side: str, amount: Decimal, take_profit_price: Decimal) -> Optional[Dict]:
        ext = _to_external_symbol(symbol)
        try:
            oid = self._next_order_id()
            self.pending_orders[oid] = {
                "id": oid,
                "symbol": ext,
                "type": "take_profit_market",
                "side": side.lower(),
                "amount": float(amount),
                "stopPrice": float(take_profit_price),
                "status": "open",
            }
            return self.pending_orders[oid]
        except Exception as e:
            print(f"BinanceAdapter.place_take_profit failed: symbol={ext}, err={e}")
            return None

    def update_stop_loss(self, symbol: str, order_id: str, new_stop_price: Decimal) -> Optional[Dict]:
        ext = _to_external_symbol(symbol)
        try:
            o = self.pending_orders.get(order_id)
            if not o or o.get("symbol") != ext:
                return None
            o["stopPrice"] = float(new_stop_price)
            return o
        except Exception as e:
            print(f"BinanceAdapter.update_stop_loss failed: order_id={order_id}, err={e}")
            return None

    def update_stop_loss_to_entry(self, symbol: str, order_id: str) -> Optional[Dict]:
        ext = _to_external_symbol(symbol)
        with self._lock:
            entry = self.entry_prices.get(ext)
            if entry is None:
                print(f"No entry price found for {ext}")
                return None
            return self.update_stop_loss(ext, order_id, entry)

    # ========== Internal Execution Logic (Simulation) ==========

    def _execute_order(
        self,
        symbol: str,   # external symbol key
        side: str,
        amount: Decimal,
        price: Decimal,
        order_type: str = "market",
        timestamp: Any = None
    ) -> Dict:
        with self._lock:
            fee_rate = self.maker_fee if order_type == "limit" else self.taker_fee
            notional = amount * price
            margin_required = notional / self.leverage
            fee = notional * fee_rate

            current_position = self.positions.get(symbol, Decimal("0"))
            realized_pnl = Decimal("0")

            if side == "buy":
                new_position, realized_pnl = self._execute_buy(
                    symbol, amount, price, current_position,
                    margin_required, fee, fee_rate, timestamp
                )
            else:
                new_position, realized_pnl = self._execute_sell(
                    symbol, amount, price, current_position,
                    margin_required, fee, fee_rate, timestamp
                )

            self._update_position(symbol, new_position)

            trade_record = {
                "timestamp": timestamp,
                "symbol": symbol,
                "side": side,
                "amount": float(amount),
                "price": float(price),
                "fee": float(fee),
                "realized_pnl": float(realized_pnl),
                "balance": float(self.balance),
                "position": float(new_position),
            }
            self.trade_history.append(trade_record)

            return {
                "id": self._next_order_id(),
                "symbol": symbol,
                "type": order_type,
                "side": side,
                "amount": float(amount),
                "price": float(price),
                "fee": float(fee),
                "realized_pnl": float(realized_pnl),
                "timestamp": timestamp,
                "status": "closed",
            }

    def _execute_buy(
        self,
        symbol: str,
        amount: Decimal,
        price: Decimal,
        current_position: Decimal,
        margin_required: Decimal,
        fee: Decimal,
        fee_rate: Decimal,
        timestamp: Any
    ) -> tuple[Decimal, Decimal]:
        realized_pnl = Decimal("0")
        if current_position >= 0:
            new_position = self._open_long(symbol, amount, price, current_position, margin_required, fee, timestamp)
        else:
            new_position, realized_pnl = self._close_short(symbol, amount, price, current_position, fee, fee_rate, timestamp)
        return new_position, realized_pnl

    def _execute_sell(
        self,
        symbol: str,
        amount: Decimal,
        price: Decimal,
        current_position: Decimal,
        margin_required: Decimal,
        fee: Decimal,
        fee_rate: Decimal,
        timestamp: Any
    ) -> tuple[Decimal, Decimal]:
        realized_pnl = Decimal("0")
        if current_position <= 0:
            new_position = self._open_short(symbol, amount, price, current_position, margin_required, fee, timestamp)
        else:
            new_position, realized_pnl = self._close_long(symbol, amount, price, current_position, fee, fee_rate, timestamp)
        return new_position, realized_pnl

    def _open_long(
        self,
        symbol: str,
        amount: Decimal,
        price: Decimal,
        current_position: Decimal,
        margin_required: Decimal,
        fee: Decimal,
        timestamp: Any
    ) -> Decimal:
        total_cost = margin_required + fee
        if self.balance < total_cost:
            raise ValueError(f"Insufficient balance: need {total_cost}, have {self.balance}")

        self.balance -= total_cost
        self.margin_used[symbol] = self.margin_used.get(symbol, Decimal("0")) + margin_required

        if current_position == 0:
            self.entry_prices[symbol] = price
            self.entry_times[symbol] = timestamp
        else:
            old_entry = self.entry_prices[symbol]
            total_position = current_position + amount
            self.entry_prices[symbol] = (old_entry * current_position + price * amount) / total_position

        return current_position + amount

    def _open_short(
        self,
        symbol: str,
        amount: Decimal,
        price: Decimal,
        current_position: Decimal,
        margin_required: Decimal,
        fee: Decimal,
        timestamp: Any
    ) -> Decimal:
        total_cost = margin_required + fee
        if self.balance < total_cost:
            raise ValueError(f"Insufficient balance: need {total_cost}, have {self.balance}")

        self.balance -= total_cost
        self.margin_used[symbol] = self.margin_used.get(symbol, Decimal("0")) + margin_required

        if current_position == 0:
            self.entry_prices[symbol] = price
            self.entry_times[symbol] = timestamp
        else:
            old_entry = self.entry_prices[symbol]
            total_position = abs(current_position) + amount
            self.entry_prices[symbol] = (old_entry * abs(current_position) + price * amount) / total_position

        return current_position - amount

    def _close_short(
        self,
        symbol: str,
        amount: Decimal,
        price: Decimal,
        current_position: Decimal,
        fee: Decimal,
        fee_rate: Decimal,
        timestamp: Any
    ) -> tuple[Decimal, Decimal]:
        close_amount = min(abs(current_position), amount)
        remaining_amount = amount - close_amount

        entry_price = self.entry_prices.get(symbol, price)
        realized_pnl = close_amount * (entry_price - price)

        closed_notional = close_amount * entry_price
        released_margin = closed_notional / self.leverage
        self.margin_used[symbol] = max(Decimal("0"), self.margin_used.get(symbol, Decimal("0")) - released_margin)

        self.balance += realized_pnl - fee
        new_position = current_position + close_amount

        if remaining_amount > 0:
            # flip to long
            new_position = self._open_long(
                symbol, remaining_amount, price, new_position,
                (remaining_amount * price) / self.leverage,
                (remaining_amount * price) * fee_rate,
                timestamp
            )
        elif new_position == 0:
            self._clear_position_tracking(symbol)

        return new_position, realized_pnl

    def _close_long(
        self,
        symbol: str,
        amount: Decimal,
        price: Decimal,
        current_position: Decimal,
        fee: Decimal,
        fee_rate: Decimal,
        timestamp: Any
    ) -> tuple[Decimal, Decimal]:
        close_amount = min(current_position, amount)
        remaining_amount = amount - close_amount

        entry_price = self.entry_prices.get(symbol, price)
        realized_pnl = close_amount * (price - entry_price)

        closed_notional = close_amount * entry_price
        released_margin = closed_notional / self.leverage
        self.margin_used[symbol] = max(Decimal("0"), self.margin_used.get(symbol, Decimal("0")) - released_margin)

        self.balance += realized_pnl - fee
        new_position = current_position - close_amount

        if remaining_amount > 0:
            # flip to short
            new_position = self._open_short(
                symbol, remaining_amount, price, new_position,
                (remaining_amount * price) / self.leverage,
                (remaining_amount * price) * fee_rate,
                timestamp
            )
        elif new_position == 0:
            self._clear_position_tracking(symbol)

        return new_position, realized_pnl

    def _update_position(self, symbol: str, new_position: Decimal):
        if new_position == 0:
            self.positions.pop(symbol, None)
            self.margin_used.pop(symbol, None)
        else:
            self.positions[symbol] = new_position

    def _clear_position_tracking(self, symbol: str):
        self.entry_prices.pop(symbol, None)
        self.entry_times.pop(symbol, None)
