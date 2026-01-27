"""
Manual test for BinanceAdapter.create_order() on Binance Futures Testnet

Covers:
1) Market BUY -> Verify Position -> Market SELL (close)
2) Limit BUY (Unfilled) -> Verify Open -> Cancel
3) Multiple symbols execution

Run:
  python test_create_order.py

Requirements:
- BINANCE_API_KEY and BINANCE_SECRET_KEY (Testnet credentials) in .env
"""

import os
import sys
import time
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
    else:
        load_dotenv()
except ImportError:
    pass

from app.services.execution.cex.binance_adapter import BinanceAdapter

def banner(title: str):
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)

def test_market_buy_sell(adapter: BinanceAdapter):
    banner("TEST 1: Market BUY -> Market SELL (Real Testnet)")

    symbol = "BTC/USDT:USDT"
    qty = Decimal("0.01") # Ensure this is above min notional (~$5)

    # 1. Check Price
    ticker = adapter.client.fetch_ticker(symbol)
    print(f"Current price: {ticker['last']}")

    # 2. Check Balance
    bal = adapter.fetch_balance()
    start_usdt = bal.get("USDT", {}).get("total", 0)
    print(f"Start Balance (USDT): {start_usdt}")

    # 3. Place BUY
    print(f"Sending Market BUY for {qty} BTC...")
    buy_order = adapter.create_order(
        symbol=symbol,
        order_type="market",
        side="buy",
        amount=qty,
    )
    print("BUY Response:", buy_order.get('status'), buy_order.get('id'))

    time.sleep(2) # Wait for API propagation

    # 4. Verify Position
    positions = adapter.fetch_positions([symbol])
    print("Positions:", [f"{p['symbol']}: {p['contracts']}" for p in positions])
    
    # Find specific position
    pos = next((p for p in positions if p['symbol'] == symbol), None)
    assert pos is not None, "Position not found after BUY"
    assert float(pos['contracts']) >= float(qty), f"Position size mismatch: {pos['contracts']} < {qty}"

    # 5. Place SELL (Close)
    print("Sending Market SELL to close...")
    sell_order = adapter.create_order(
        symbol=symbol,
        order_type="market",
        side="sell",
        amount=qty,
    )
    print("SELL Response:", sell_order.get('status'), sell_order.get('id'))

    time.sleep(2)

    # 6. Verify Empty
    positions = adapter.fetch_positions([symbol])
    # Position might disappear or show as 0 contracts
    contracts = positions[0]['contracts'] if positions else 0
    print(f"Final Contracts: {contracts}")
    assert contracts == 0, f"Position did not close completely, left: {contracts}"


def test_limit_order_cancel(adapter: BinanceAdapter):
    banner("TEST 2: Limit BUY (Placed -> Verified -> Cancelled)")

    symbol = "BTC/USDT:USDT"
    qty = Decimal("0.005")

    # 1. Get Price
    ticker = adapter.client.fetch_ticker(symbol)
    current_price = Decimal(str(ticker["last"]))
    # Place limit well below market so it doesn't fill immediately
    limit_price = current_price * Decimal("0.90")
    
    print(f"Market: {current_price} | Limit Price: {limit_price}")

    # 2. Place Limit Order
    print("Placing Limit Order...")
    order = adapter.create_order(
        symbol=symbol,
        order_type="limit",
        side="buy",
        amount=qty,
        price=limit_price,
    )
    print("Order Response:", order)
    order_id = order.get('id')

    assert order.get('status') in ['new', 'open'], f"Order status was {order.get('status')}"

    time.sleep(1)

    # 3. Cancel Order
    print(f"Cancelling Order ID: {order_id}")
    result = adapter.cancel_order(order_id, symbol)
    assert result is True, "Cancel order failed"
    print("Order cancelled successfully.")


def test_multiple_symbols(adapter: BinanceAdapter):
    banner("TEST 3: Multiple Symbols (BTC & ETH)")

    symbols = ["BTC/USDT:USDT", "ETH/USDT:USDT"]
    # Adjust qty for valid min-notional (e.g. 0.01 ETH is ~$25, 0.002 BTC is ~$100)
    qtys = {
        "BTC/USDT:USDT": Decimal("0.005"),
        "ETH/USDT:USDT": Decimal("0.02")
    }

    # 1. Buy Both
    for s in symbols:
        print(f"Buying {s}...")
        adapter.create_order(
            symbol=s,
            order_type="market",
            side="buy",
            amount=qtys[s],
        )
    
    time.sleep(2)

    # 2. Verify positions
    positions = adapter.fetch_positions(symbols)
    print("Positions:", [f"{p['symbol']}: {p['contracts']}" for p in positions])
    
    assert len(positions) == 2, f"Expected 2 positions, got {len(positions)}"

    # 3. Sell Both (Cleanup)
    print("Closing all positions...")
    for s in symbols:
        adapter.create_order(
            symbol=s,
            order_type="market",
            side="sell",
            amount=qtys[s],
        )

    time.sleep(2)
    final_pos = adapter.fetch_positions(symbols)
    assert len(final_pos) == 0 or all(p['contracts'] == 0 for p in final_pos), f"Positions failed to close: {final_pos}"


def main():
    banner("BINANCE ADAPTER - TESTNET INTEGRATION TEST")

    # Ensure keys exist
    if not (os.getenv("BINANCE_API_KEY") or os.getenv("BINANCE_TESTNET_API_KEY")):
        print("ERROR: Missing BINANCE_API_KEY / SECRET in .env")
        return

    # Initialize Adapter (Paper mode now = Testnet)
    adapter = BinanceAdapter(
        config={"bot": {"mode": "paper"}},
        initial_balance=1000.0, # Ignored in real testnet
        leverage=20, # Will attempt to set leverage on testnet
    )

    try:
        test_market_buy_sell(adapter)
        test_limit_order_cancel(adapter)
        test_multiple_symbols(adapter)
        banner("ALL TESTS PASSED ✅")
        
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        
        # Emergency Cleanup Attempt
        print("\nAttempting emergency cleanup...")
        try:
            adapter.cancel_orders_for_symbol("BTC/USDT:USDT")
            adapter.cancel_orders_for_symbol("ETH/USDT:USDT")
        except:
            pass

if __name__ == "__main__":
    main()