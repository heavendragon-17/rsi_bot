import os
import pandas as pd
import threading
from decimal import Decimal
from typing import Any, Dict, List, Optional
from dataclasses import dataclass
from pathlib import Path

import ccxt
from binance.um_futures import UMFutures
from binance.error import ClientError

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
      - orders are EXECUTED on Binance Futures TESTNET via self._um
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

        # Simulated account state (Kept for fallback, but Paper now uses Testnet)
        self.balance = to_decimal(initial_balance)
        self.leverage = Decimal(str(leverage))
        self.maker_fee = Decimal(str(maker_fee))
        self.taker_fee = Decimal(str(taker_fee))

        # Simulation bookkeeping (CCXT-style keys) - UNUSED IN TESTNET MODE
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
        # Binance Futures DEMO client
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

            # ============================================================ 
            # PAPER MODE - TESTNET
            # ============================================================ 
            try:
                account = self._um.account()
                # Find USDT asset
                usdt = next((a for a in account['assets'] if a['asset'] == 'USDT'), None)
                if not usdt:
                    return {}
                
                free = float(usdt['availableBalance'])
                total = float(usdt['walletBalance'])
                used = total - free
                
                return {
                    "USDT": {
                        "free": free,
                        "used": used,
                        "total": total,
                    },
                    "free": {"USDT": free},
                    "used": {"USDT": used},
                    "total": {"USDT": total},
                }
            except Exception as e:
                print(f"BinanceAdapter.fetch_balance (Testnet) failed: {e}")
                return {}

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

            # ============================================================ 
            # PAPER MODE - TESTNET
            # ============================================================ 
            try:
                # 1. Fetch all positions from Binance (Testnet)
                all_pos = self._um.get_position_risk()
                
                pos_list: List[Dict] = []
                # Convert requested symbols to UM format (e.g. "BTCUSDT") for filtering
                wanted_um = {_to_um_symbol(s) for s in symbols} if symbols else None

                for p in all_pos:
                    # p is a dict like {'symbol': 'BTCUSDT', 'positionAmt': '0.001', ...}
                    
                    # 2. Filter by symbol if requested
                    if wanted_um and p.get('symbol') not in wanted_um:
                        continue
                    
                    # 3. Check Position Amount (using .get for safety)
                    raw_amt = p.get('positionAmt', "0")
                    amt = float(raw_amt)
                    
                    if amt == 0:
                        continue
                        
                    # 4. Robust Data Extraction
                    try:
                        sym_ext = _to_external_symbol(p.get('symbol'))
                        
                        pos_list.append({
                            "symbol": sym_ext,
                            "contracts": abs(amt),
                            "contractSize": 1.0,
                            # Use .get() with defaults for safety to avoid KeyErrors
                            "unrealizedPnl": float(p.get('unRealizedProfit', 0)),
                            "leverage": float(p.get('leverage', 1)), 
                            "entryPrice": float(p.get('entryPrice', 0)),
                            "side": "long" if amt > 0 else "short",
                            "notional": float(p.get('notional', 0)),
                            "markPrice": float(p.get('markPrice', 0)),
                            "info": p,
                        })
                    except Exception as inner_e:
                        print(f"⚠️ Error parsing position for {p.get('symbol')}: {inner_e}")
                        print(f"Raw Data: {p}") 
                        continue

                return pos_list

            except Exception as e:
                print(f"BinanceAdapter.fetch_positions (Testnet) failed: {e}")
                return []

    def set_leverage(self, symbol: str, leverage: int) -> bool:
        ext = _to_external_symbol(symbol)
        um_sym = _to_um_symbol(ext)
        try:
            with self._lock:
                if self.mode == "live":
                    self.client.set_leverage(leverage, ext)
                else:
                    # ============================================================ 
                    # PAPER MODE - TESTNET
                    # ============================================================ 
                    self._um.change_leverage(symbol=um_sym, leverage=leverage)
                
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

        # ============================================================ 
        # PAPER MODE - TESTNET
        # ============================================================ 
        try:
            um_sym = _to_um_symbol(ext)
            
            params = {
                "symbol": um_sym,
                "side": side_l.upper(),
                "type": order_type_l.upper(),
                "quantity": float(amount),
            }
            
            if price is not None:
                params["price"] = float(price)
            
            if order_type_l == "limit":
                params["timeInForce"] = "GTC"
                
            # Execute on Demo FAPI
            resp = self._um.new_order(**params)
            
            # Normalize response to resemble CCXT return
            return {
                "id": str(resp.get("orderId")),
                "symbol": ext,
                "type": resp.get("type").lower(),
                "side": resp.get("side").lower(),
                "amount": float(resp.get("origQty", 0)),
                "price": float(resp.get("price", 0) or 0),
                "status": resp.get("status").lower(),
                "info": resp
            }
            
        except ClientError as e:
            print(f"Testnet create_order failed: {e.error_message}")
            return {"status": "failed", "error": e.error_message}
        except Exception as e:
            print(f"Testnet create_order unexpected error: {e}")
            return {"status": "failed", "error": str(e)}

    def cancel_order(self, order_id: str, symbol: str) -> bool:
        ext = _to_external_symbol(symbol)
        try:
            if self.mode == "live":
                self.client.cancel_order(order_id, ext)
                return True
            
            # ============================================================ 
            # PAPER MODE - TESTNET
            # ============================================================ 
            um_sym = _to_um_symbol(ext)
            # order_id might be "mock_order_X" if left over, but new orders are ints
            # Try converting to int, if fails it might be a mock ID which we can't cancel on real chain
            try:
                oid_int = int(order_id)
                self._um.cancel_order(symbol=um_sym, orderId=oid_int)
            except ValueError:
                # If it's a mock string from old logic, just ignore or handle locally
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

            # ============================================================ 
            # PAPER MODE - TESTNET
            # ============================================================ 
            um_sym = _to_um_symbol(ext)
            self._um.cancel_open_orders(symbol=um_sym)
            return True
        except Exception as e:
            print(f"BinanceAdapter.cancel_orders_for_symbol failed: symbol={ext}, err={e}")
            return False

    # ========== Stop Loss / Take Profit (Real execution on Testnet) ==========

    def place_stop_loss(self, symbol: str, side: str, amount: Decimal, stop_price: Decimal) -> Optional[Dict]:
        """
        Submits a STOP_MARKET order to Binance Futures (Testnet or Live)
        """
        ext = _to_external_symbol(symbol)
        um_sym = _to_um_symbol(ext)
        side_l = side.lower()
        
        try:
            # Note: SL side is opposite to position. If Long, SL is SELL.
            params = {
                "symbol": um_sym,
                "side": side.upper(), 
                "type": "STOP_MARKET",
                "stopPrice": float(stop_price),
                "closePosition": "true", # Usually SL closes position
            }
            # Alternatively, if not closePosition=True, you must specify quantity
            # params["quantity"] = float(amount)

            if self.mode == "live":
                # CCXT implementation needed or raw call
                pass
            
            # ============================================================ 
            # PAPER MODE - TESTNET
            # ============================================================ 
            resp = self._um.new_order(**params)
            return {
                "id": str(resp.get("orderId")),
                "symbol": ext,
                "type": "stop_market",
                "stopPrice": float(stop_price),
                "status": "open",
                "info": resp
            }
            
        except Exception as e:
            print(f"BinanceAdapter.place_stop_loss failed: symbol={ext}, err={e}")
            return None

    def place_take_profit(self, symbol: str, side: str, amount: Decimal, take_profit_price: Decimal) -> Optional[Dict]:
        """
        Submits a TAKE_PROFIT_MARKET order to Binance Futures
        """
        ext = _to_external_symbol(symbol)
        um_sym = _to_um_symbol(ext)
        
        try:
            params = {
                "symbol": um_sym,
                "side": side.upper(),
                "type": "TAKE_PROFIT_MARKET",
                "stopPrice": float(take_profit_price),
                "closePosition": "true", 
            }
            
            # ============================================================ 
            # PAPER MODE - TESTNET
            # ============================================================ 
            resp = self._um.new_order(**params)
            return {
                "id": str(resp.get("orderId")),
                "symbol": ext,
                "type": "take_profit_market",
                "stopPrice": float(take_profit_price),
                "status": "open",
                "info": resp
            }
        except Exception as e:
            print(f"BinanceAdapter.place_take_profit failed: symbol={ext}, err={e}")
            return None

    def update_stop_loss(self, symbol: str, order_id: str, new_stop_price: Decimal) -> Optional[Dict]:
        ext = _to_external_symbol(symbol)
        # Binance doesn't support "update" easily, usually Cancel + Replace
        # Implementation left simple for now
        self.cancel_order(order_id, symbol)
        # Note: We'd need to know the original side/amount to replace it. 
        # For this snippet, just cancelling old one.
        print(f"Order {order_id} cancelled. Please place new SL manually or via bot logic.")
        return None

    def update_stop_loss_to_entry(self, symbol: str, order_id: str) -> Optional[Dict]:
        # Logic depends on tracking entry price, which we fetch from API now
        ext = _to_external_symbol(symbol)
        positions = self.fetch_positions([symbol])
        if not positions:
            return None
        
        entry = positions[0]['entryPrice']
        return self.update_stop_loss(symbol, order_id, Decimal(str(entry)))
