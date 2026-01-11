import os
import ccxt
import pandas as pd
from decimal import Decimal
from typing import Any, Dict, List, Optional

from app.core.interfaces import IExchange

class BinanceAdapter(IExchange):
    """
    Binance adapter using CCXT.

    If you use binanceusdm (USDT-M futures), symbols should be like:
      BTC/USDT:USDT

    Spot symbols are like:
      BTC/USDT
    """

    def __init__(self, config: dict):
        self.config = config or {}
        bot_cfg = self.config.get("bot", {})
        self.mode = (bot_cfg.get("mode") or "paper").lower()  # "paper" or "live"

        # Choose keys depending on mode (optional)
        # If you only have one pair of keys, keep BINANCE_API_KEY/BINANCE_SECRET_KEY.
        if self.mode == "paper":
            api_key = os.getenv("BINANCE_TESTNET_API_KEY") or os.getenv("BINANCE_API_KEY")
            secret = os.getenv("BINANCE_TESTNET_SECRET_KEY") or os.getenv("BINANCE_SECRET_KEY")
        else:
            api_key = os.getenv("BINANCE_API_KEY")
            secret = os.getenv("BINANCE_SECRET_KEY")

        if not api_key or not secret:
            raise RuntimeError("Missing BINANCE_API_KEY / BINANCE_SECRET_KEY env vars.")

        # USDT-M futures
        self.client = ccxt.binanceusdm({
            "apiKey": api_key,
            "secret": secret,
            "enableRateLimit": True,
            "options": {
                # important: futures defaultType
                "defaultType": "future",
            }
        })

        # If paper mode uses testnet, you must set testnet endpoint for futures
        # CCXT supports set_sandbox_mode on many exchanges; for binanceusdm it generally works.
        if self.mode == "paper":
            try:
                self.client.set_sandbox_mode(True)
            except Exception:
                # If sandbox mode isn't supported in your ccxt version,
                # you must set urls manually. (But try sandbox first.)
                pass

        # CRITICAL: load markets once
        self.client.load_markets()

    # ---------- helpers ----------

    def _normalize_symbol(self, symbol: str) -> str:
        """
        Convert spot-like symbol to futures symbol if needed.
        For binanceusdm, the common CCXT symbol is BTC/USDT:USDT.
        """
        s = (symbol or "").strip()
        if not s:
            return s

        # If already futures-format, keep it
        if ":" in s:
            return s

        # Convert BTC/USDT -> BTC/USDT:USDT for USDT-M futures
        if s.endswith("/USDT"):
            return f"{s}:USDT"

        return s

    # ---------- required interface methods ----------

    def fetch_ohlcv(self, symbol: str, timeframe: str, limit: int) -> List[List[Any]]:
        """
        Returns list of candles:
        [timestamp(ms), open, high, low, close, volume]
        """
        symbol = self._normalize_symbol(symbol)

        # Ensure markets loaded (safe if called multiple times)
        if not getattr(self.client, "markets", None):
            self.client.load_markets()

        return self.client.fetch_ohlcv(symbol, timeframe, limit=limit)

    def create_order(self, symbol: str, order_type: str, side: str, amount: Decimal, price: Optional[Decimal] = None):
        symbol = self._normalize_symbol(symbol)

        # CCXT wants float for amount/price typically
        amt = float(amount) if isinstance(amount, Decimal) else float(Decimal(str(amount)))
        prc = None if price is None else (float(price) if isinstance(price, Decimal) else float(Decimal(str(price))))

        params: Dict[str, Any] = {}
        return self.client.create_order(symbol, order_type, side, amt, prc, params)

    def get_balances(self, coins: Optional[List[str]] = None) -> Dict[str, Decimal]:
        """
        Return balances for a list of coins.
        If coins is None -> return all non-zero balances.
        """
        bal = self.client.fetch_balance()

        # CCXT balance structure: bal['total'] contains totals by coin
        totals = bal.get("total") or {}
        out: Dict[str, Decimal] = {}

        if coins:
            for c in coins:
                v = totals.get(c)
                if v is not None:
                    out[c] = Decimal(str(v))
            return out

        # Otherwise return all non-zero totals
        for coin, v in totals.items():
            try:
                dv = Decimal(str(v))
            except Exception:
                continue
            if dv != 0:
                out[coin] = dv
        return out

    def get_balance_of(self, assets: List[str]) -> Dict[str, Decimal]:
        """
        REQUIRED by your IExchange (based on earlier error).

        Example:
          get_balance_of(["USDT", "BTC", "ETH"])
          -> {"USDT": Decimal("123.4"), "BTC": Decimal("0.01"), "ETH": Decimal("0")}
        """
        assets_norm = [a.strip().upper() for a in assets if a and a.strip()]
        if not assets_norm:
            return {}

        bal = self._fetch_balances_raw()
        totals = bal.get("total") or {}

        out: Dict[str, Decimal] = {}
        for a in assets_norm:
            out[a] = Decimal(str(totals.get(a, 0) or 0))
        return out
    
    def fetch_candles_df_multi(
        self,
        symbols: List[str],
        timeframe: str,
        limit: int = 500,
    ) -> Dict[str, pd.DataFrame]:
        """
        Fetch OHLCV candles for multiple symbols.

        Usage:
        ex = BinanceAdapter(config)
        symbols = ["BTC/USDT", "ETH/USDT"]
        dfs = ex.fetch_candles_df_multi(symbols, "1h", limit=200)

        Returns:
        {
            "BTC/USDT": DataFrame,
            "ETH/USDT": DataFrame,
        }

        DataFrame columns:
        timestamp, open, high, low, close, volume
        """
        out: Dict[str, pd.DataFrame] = {}

        for symbol in symbols:
            raw = self.fetch_ohlcv(symbol, timeframe, limit)

            df = pd.DataFrame(
                raw,
                columns=["timestamp", "open", "high", "low", "close", "volume"],
            )
            df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
            df = df.set_index("timestamp")

            out[symbol] = df

        return out
    
    def cancel_order(self, order_id: str, symbol: str) -> bool:
        """
        Cancel a single order.
        Returns True if request succeeded, False otherwise.
        """
        try:
            self.client.cancel_order(order_id, symbol)
            return True
        except Exception as e:
            # You can replace print with logger if you have one
            print(f"BinanceAdapter.cancel_order failed: order_id={order_id}, symbol={symbol}, err={e}")
            return False
