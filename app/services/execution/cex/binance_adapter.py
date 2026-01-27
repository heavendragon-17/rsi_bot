import os
import time
import math
import threading
import pandas as pd
from decimal import Decimal, ROUND_FLOOR
from typing import Any, Dict, List, Optional
from dataclasses import dataclass
from pathlib import Path

import ccxt
from binance.um_futures import UMFutures
from binance.error import ClientError

# Load environment variables
try:
    from dotenv import load_dotenv
    env_path = Path(__file__).parent.parent.parent.parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)
    else:
        load_dotenv()
except ImportError:
    pass

# ==============================================================================
# 1. HELPER FUNCTIONS (Symbol Normalization)
# ==============================================================================

def to_decimal(val) -> Decimal:
    if val is None: return Decimal("0")
    if isinstance(val, Decimal): return val
    return Decimal(str(val))

def _to_external_symbol(symbol: str) -> str:
    """Normalize to CCXT futures style: BTC/USDT:USDT"""
    s = (symbol or "").strip().upper()
    if not s: return s
    if "/" in s and ":" in s: return s
    if "/" in s and ":" not in s: return f"{s}:USDT"
    if s.endswith("USDT") and "/" not in s:
        base = s[:-4]
        return f"{base}/USDT:USDT"
    return s

def _to_um_symbol(symbol: str) -> str:
    """Convert external to UMFutures symbol: BTCUSDT"""
    s = (symbol or "").strip().upper()
    if not s: return s
    if ":" in s: s = s.split(":", 1)[0]
    if "/" in s:
        base, quote = s.split("/", 1)
        return f"{base}{quote}"
    return s

# ==============================================================================
# 2. PAPER CLIENT WRAPPER (Mimics CCXT)
# ==============================================================================

class UMFuturesPaperClient:
    """
    Wraps binance-connector (UMFutures) to behave exactly like CCXT
    but operates on the Binance Testnet.
    """
    def __init__(self, api_key, secret):
        self.um = UMFutures(
            key=api_key, 
            secret=secret, 
            base_url="https://demo-fapi.binance.com"
        )

    def fetch_ticker(self, symbol: str) -> Dict[str, Any]:
        ext = _to_external_symbol(symbol)
        um_sym = _to_um_symbol(ext)
        t = self.um.ticker_price(symbol=um_sym)
        return {
            "symbol": ext,
            "last": float(t["price"]),
            "info": t,
        }

    def fetch_ohlcv(self, symbol: str, timeframe: str, limit: int = 500) -> List[List[Any]]:
        ext = _to_external_symbol(symbol)
        um_sym = _to_um_symbol(ext)
        tf_map = {
            "1m": "1m", "3m": "3m", "5m": "5m", "15m": "15m", "30m": "30m",
            "1h": "1h", "2h": "2h", "4h": "4h", "6h": "6h", "8h": "8h", 
            "1d": "1d", "1w": "1w",
        }
        interval = tf_map.get(timeframe, timeframe)
        try:
            data = self.um.klines(symbol=um_sym, interval=interval, limit=limit)
        except ClientError:
            time.sleep(1)
            data = self.um.klines(symbol=um_sym, interval=interval, limit=limit)

        out = []
        for k in data:
            out.append([k[0], float(k[1]), float(k[2]), float(k[3]), float(k[4]), float(k[5])])
        return out

    def fetch_order(self, order_id: str, symbol: str) -> Dict[str, Any]:
        ext = _to_external_symbol(symbol)
        um_sym = _to_um_symbol(ext)
        try:
            resp = self.um.query_order(symbol=um_sym, orderId=int(order_id))
            return self._normalize_order(resp, ext)
        except ClientError as e:
            if e.error_code == -2013: # Order does not exist (latency)
                return {"id": str(order_id), "status": "unknown", "symbol": ext}
            raise e

    def create_order(self, symbol: str, type: str, side: str, amount: float, price: float = None, params={}) -> Dict[str, Any]:
        ext = _to_external_symbol(symbol)
        um_sym = _to_um_symbol(ext)
        
        req = {
            "symbol": um_sym,
            "side": side.upper(),
            "type": type.upper(),
            "quantity": float(amount),
        }
        if price:
            req["price"] = float(price)
        if type.lower() == "limit":
            req["timeInForce"] = "GTC"
        
        # Merge extra params (like stopPrice for SL/TP)
        req.update(params)

        try:
            resp = self.um.new_order(**req)
            return self._normalize_order(resp, ext)
        except ClientError as e:
            return {"status": "failed", "error": e.error_message}

    def cancel_order(self, id: str, symbol: str):
        ext = _to_external_symbol(symbol)
        um_sym = _to_um_symbol(ext)
        try:
            self.um.cancel_order(symbol=um_sym, orderId=int(id))
            return True
        except ClientError:
            return False

    def fetch_positions(self, symbols: List[str] = None) -> List[Dict]:
        all_pos = self.um.get_position_risk()
        wanted_um = {_to_um_symbol(s) for s in symbols} if symbols else None
        pos_list = []
        
        for p in all_pos:
            if wanted_um and p['symbol'] not in wanted_um: continue
            amt = float(p.get('positionAmt', 0))
            if amt == 0: continue
            
            sym_ext = _to_external_symbol(p['symbol'])
            pos_list.append({
                "symbol": sym_ext,
                "contracts": abs(amt),
                "entryPrice": float(p.get('entryPrice', 0)),
                "side": "long" if amt > 0 else "short",
                "info": p
            })
        return pos_list

    def fetch_balance(self):
        account = self.um.account()
        usdt = next((a for a in account['assets'] if a['asset'] == 'USDT'), None)
        if not usdt: return {}
        free = float(usdt['availableBalance'])
        total = float(usdt['walletBalance'])
        return {"free": {"USDT": free}, "total": {"USDT": total}}

    def _normalize_order(self, resp, symbol):
        return {
            "id": str(resp.get("orderId")),
            "symbol": symbol,
            "status": resp.get("status").lower(),
            "price": float(resp.get("price", 0)),
            "amount": float(resp.get("origQty", 0)),
            "side": resp.get("side").lower(),
            "type": resp.get("type").lower(),
            "info": resp
        }

# ==============================================================================
# 3. BINANCE ADAPTER (The Main Interface)
# ==============================================================================

class BinanceAdapter:
    """
    Unified Interface for Binance Futures.
    Can switch between 'live' and 'paper' modes dynamically.
    Exposes direct methods so you don't need to call adapter.client.xxx
    """

    def __init__(self, config: dict = None, initial_balance: float = 1000.0):
        self.config = config or {}
        
        # 1. Initialize Clients (Lazy load would be better, but init both for now)
        self._live_client = None
        self._paper_client = None
        
        self._init_live_client()
        self._init_paper_client()
        
        # 2. Set Default Mode
        self._mode = "paper"
        if self.config.get("bot", {}).get("mode") == "live":
            self._mode = "live"

    # --- Mode Management ---

    @property
    def mode(self):
        return self._mode

    @mode.setter
    def mode(self, value: str):
        if value not in ["live", "paper"]:
            raise ValueError("Mode must be 'live' or 'paper'")
        self._mode = value
        print(f"🔄 Switched BinanceAdapter to {self._mode.upper()} mode.")

    @property
    def client(self):
        """Returns the underlying client based on current mode."""
        if self._mode == "live":
            if not self._live_client: raise RuntimeError("Live Client not initialized (check keys)")
            return self._live_client
        else:
            if not self._paper_client: raise RuntimeError("Paper Client not initialized (check keys)")
            return self._paper_client

    # --- Initialization Internal ---

    def _init_live_client(self):
        key = os.getenv("BINANCE_API_KEY")
        sec = os.getenv("BINANCE_SECRET_KEY")
        if key and sec:
            self._live_client = ccxt.binanceusdm({
                "apiKey": key, "secret": sec,
                "enableRateLimit": True, "options": {"defaultType": "future"}
            })
            # self._live_client.load_markets() # Optional: load on demand to save startup time

    def _init_paper_client(self):
        key = os.getenv("BINANCE_TESTNET_API_KEY") or os.getenv("BINANCE_API_KEY")
        sec = os.getenv("BINANCE_TESTNET_SECRET_KEY") or os.getenv("BINANCE_SECRET_KEY")
        if key and sec:
            self._paper_client = UMFuturesPaperClient(key, sec)

    # ==========================================================================
    # PUBLIC API METHODS (Dispatch to self.client)
    # ==========================================================================

    def fetch_ticker(self, symbol: str) -> Dict[str, Any]:
        return self.client.fetch_ticker(symbol)

    def fetch_ohlcv(self, symbol: str, timeframe: str, limit: int = 500) -> List[List[Any]]:
        return self.client.fetch_ohlcv(symbol, timeframe, limit)

    def fetch_balance(self) -> Dict[str, Any]:
        return self.client.fetch_balance()

    def fetch_order(self, order_id: str, symbol: str) -> Dict[str, Any]:
        return self.client.fetch_order(order_id, symbol)

    def fetch_positions(self, symbols: Optional[List[str]] = None) -> List[Dict]:
        # CCXT live client needs slight arg adjustment usually, but wrapper handles it
        if self._mode == "live":
            # CCXT expects symbols list
            ext_syms = [_to_external_symbol(s) for s in symbols] if symbols else None
            pos = self.client.fetch_positions(ext_syms)
            return [p for p in pos if p.get("contracts", 0) != 0]
        else:
            return self.client.fetch_positions(symbols)

    def create_order(self, symbol: str, order_type: str, side: str, amount: Decimal, price: Optional[Decimal] = None) -> Dict:
        """
        Unified order creation.
        """
        try:
            return self.client.create_order(
                symbol=symbol,
                type=order_type,
                side=side,
                amount=float(amount),
                price=float(price) if price else None
            )
        except Exception as e:
            return {"status": "failed", "error": str(e)}

    def cancel_order(self, order_id: str, symbol: str) -> bool:
        try:
            return self.client.cancel_order(order_id, symbol)
        except Exception as e:
            print(f"Cancel failed: {e}")
            return False

    # --- Stop Loss / Take Profit Specifics ---

    def place_stop_loss(self, symbol: str, side: str, amount: Decimal, stop_price: Decimal) -> Dict:
        # Stop Loss is a STOP_MARKET order
        # Params differ slightly between CCXT and UMFutures, handled by wrapper or here
        params = {"stopPrice": float(stop_price), "closePosition": True}
        
        if self._mode == "live":
            # CCXT specific params for SL
            return self.client.create_order(symbol, "STOP_MARKET", side, float(amount), None, params)
        else:
            # Paper wrapper handles the raw params map
            return self.client.create_order(symbol, "STOP_MARKET", side, float(amount), None, params)

    # --- Helper Logic (Moved from standalone) ---

    def get_precision_info(self, symbol: str):
        """
        Fetches precision. 
        Note: CCXT has 'markets', UMFutures has 'exchange_info'.
        """
        raw_symbol = _to_um_symbol(symbol)
        
        try:
            if self._mode == "live":
                # Ensure markets are loaded
                if not self.client.markets: self.client.load_markets()
                ccxt_sym = _to_external_symbol(symbol)
                market = self.client.market(ccxt_sym)
                
                # CCXT standardizes precision
                price_prec = int(market['precision']['price'])
                qty_prec = int(market['precision']['amount'])
                return price_prec, qty_prec
            
            else:
                # Paper Mode (UMFutures)
                info = self.client.um.exchange_info()
                s_info = next((s for s in info['symbols'] if s['symbol'] == raw_symbol), None)
                if not s_info: return 2, 3
                
                # Logic to parse filters
                p_filter = next((f for f in s_info['filters'] if f['filterType'] == 'PRICE_FILTER'), None)
                q_filter = next((f for f in s_info['filters'] if f['filterType'] == 'LOT_SIZE'), None)
                
                p_prec = int(round(-math.log(float(p_filter['tickSize']), 10), 0)) if p_filter else 2
                q_prec = int(round(-math.log(float(q_filter['stepSize']), 10), 0)) if q_filter else 3
                return p_prec, q_prec

        except Exception as e:
            print(f"Precision fetch error ({self._mode}): {e}")
            return 2, 3

    # --- Utilities ---

    def check_position_active(self, symbol: str) -> bool:
        """Helper to check if a specific symbol has an open position."""
        positions = self.fetch_positions([symbol])
        target = _to_external_symbol(symbol).split(":")[0]
        
        for p in positions:
            # Normalize for comparison
            p_sym = p['symbol'].split(":")[0]
            if p_sym == target:
                if float(p.get('contracts', 0)) > 0:
                    return True
        return False