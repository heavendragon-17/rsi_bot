"""
Manual test for BinanceAdapter.create_order()

Covers:
1) Market BUY (paper, simulated)
2) Market SELL (close position)
3) Limit BUY (simulated, immediate fill)
4) Multiple symbols

Run:
  python test_create_order.py

Requirements:
- BINANCE_API_KEY or BINANCE_TESTNET_API_KEY in .env
"""

import os
import sys
from pathlib import Path
from decimal import Decimal

# Add project root to path
project_root = Path(__file__).resolve().parent
sys.path.insert(0, str(project_root))

# Load .env
try:
    from dotenv import load_dotenv
    env_path = project_root / ".env"
    if env_path.exists():
        load_dotenv(env_path)
except ImportError:
    pass

from app.services.execution.cex.binance_adapter import BinanceAdapter


def banner(title: str):
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)


def test_market_buy_sell(adapter: BinanceAdapter):
    banner("TEST 1: Market BUY → Market SELL (paper simulation)")

    symbol = "BTC/USDT:USDT"
    qty = Decimal("0.01")

    ticker = adapter.client.fetch_ticker(symbol)
    print(f"Current price: {ticker['last']}")

    start_balance = adapter.balance
    print("Start balance:", start_balance)

    buy = adapter.create_order(
        symbol=symbol,
        order_type="market",
        side="buy",
        amount=qty,
    )
    print("BUY order:", buy)

    assert symbol in adapter.positions
    assert adapter.positions[symbol] == qty

    sell = adapter.create_order(
        symbol=symbol,
        order_type="market",
        side="sell",
        amount=qty,
    )
    print("SELL order:", sell)

    assert symbol not in adapter.positions
    print("Final balance:", adapter.balance)


def test_limit_buy(adapter: BinanceAdapter):
    banner("TEST 2: Limit BUY (paper simulation, immediate fill)")

    symbol = "BTC/USDT:USDT"
    qty = Decimal("0.005")

    ticker = adapter.client.fetch_ticker(symbol)
    current_price = Decimal(str(ticker["last"]))
    limit_price = current_price * Decimal("0.98")

    print(f"Market price: {current_price}")
    print(f"Limit price:  {limit_price}")

    order = adapter.create_order(
        symbol=symbol,
        order_type="limit",
        side="buy",
        amount=qty,
        price=limit_price,
    )

    print("LIMIT BUY order:", order)

    assert symbol in adapter.positions
    assert adapter.positions[symbol] == qty

    # Clean up
    adapter.create_order(
        symbol=symbol,
        order_type="market",
        side="sell",
        amount=qty,
    )


def test_multiple_symbols(adapter: BinanceAdapter):
    banner("TEST 3: Create orders for multiple symbols")

    symbols = ["BTC/USDT:USDT", "ETH/USDT:USDT"]
    qty = Decimal("0.01")

    for s in symbols:
        t = adapter.client.fetch_ticker(s)
        print(f"{s} price: {t['last']}")

        adapter.create_order(
            symbol=s,
            order_type="market",
            side="buy",
            amount=qty,
        )

    print("Open positions:", adapter.positions)
    assert len(adapter.positions) == 2

    for s in symbols:
        adapter.create_order(
            symbol=s,
            order_type="market",
            side="sell",
            amount=qty,
        )

    print("Positions after close:", adapter.positions)
    assert len(adapter.positions) == 0


def main():
    banner("BINANCE ADAPTER - CREATE ORDER MANUAL TEST")

    if not (os.getenv("BINANCE_API_KEY") or os.getenv("BINANCE_TESTNET_API_KEY")):
        raise RuntimeError("Missing BINANCE_API_KEY or BINANCE_TESTNET_API_KEY")

    adapter = BinanceAdapter(
        config={"bot": {"mode": "paper"}},
        initial_balance=10000.0,
        leverage=10,
        maker_fee=0.0002,
        taker_fee=0.0004,
    )

    test_market_buy_sell(adapter)

    adapter2 = BinanceAdapter(
        config={"bot": {"mode": "paper"}},
        initial_balance=10000.0,
        leverage=10,
        maker_fee=0.0002,
        taker_fee=0.0004,
    )
    test_limit_buy(adapter2)

    adapter3 = BinanceAdapter(
        config={"bot": {"mode": "paper"}},
        initial_balance=10000.0,
        leverage=10,
        maker_fee=0.0002,
        taker_fee=0.0004,
    )
    test_multiple_symbols(adapter3)

    banner("ALL CREATE ORDER TESTS PASSED ✅")


if __name__ == "__main__":
    main()
