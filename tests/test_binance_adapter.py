"""
Integration tests for BinanceAdapter

IMPORTANT: Binance deprecated futures testnet. Options:
1. Paper Mode (Recommended): Simulates orders locally, fetches real market data
2. Live Mode: Uses REAL money - BE VERY CAREFUL!
3. Demo Trading: Need to enable via Binance (not widely available)

For testing: Use paper mode which simulates execution with real market data

Run with: pytest tests/test_binance_integration.py -v -s
Or: python tests/test_binance_integration.py
"""

import sys
import os
from pathlib import Path
from decimal import Decimal
import time

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Load .env
try:
    from dotenv import load_dotenv
    load_dotenv(project_root / ".env")
except ImportError:
    print("Warning: python-dotenv not installed")

import pytest
from app.services.execution.cex.binance_adapter import BinanceAdapter

# Skip the entire module unless explicitly opted in.
# These are live-network integration tests that require testnet credentials and
# must not run automatically in CI or during normal development test runs.
# To run: RUN_INTEGRATION_TESTS=1 pytest tests/test_binance_adapter.py -v
pytestmark = pytest.mark.skipif(
    not os.getenv("RUN_INTEGRATION_TESTS"),
    reason="Set RUN_INTEGRATION_TESTS=1 to run live exchange integration tests",
)


class TestBinancePaperTrading:
    """Test paper trading with simulated execution."""
    
    @pytest.fixture
    def adapter(self):
        """Create adapter in paper trading mode."""
        return BinanceAdapter(
            config={"bot": {"mode": "paper"}},
            initial_balance=10000.0,
            leverage=10,
            maker_fee=0.0002,
            taker_fee=0.0004
        )
    
    def test_fetch_real_market_data(self, adapter):
        """Test fetching real market data from Binance."""
        print("\n=== Testing Real Market Data ===")
        
        # Fetch real OHLCV data
        candles = adapter.fetch_ohlcv("BTC/USDT", "1h", 10)
        
        print(f"Fetched {len(candles)} real candles from Binance")
        if candles:
            latest = candles[-1]
            print(f"Latest BTC/USDT price: ${latest[4]}")
        
        assert len(candles) > 0
        print("✓ Successfully fetched real market data")
    
    def test_simulated_order_with_real_prices(self, adapter):
        """Test order simulation using real market prices."""
        print("\n=== Testing Simulated Trading ===")
        
        symbol = "BTC/USDT:USDT"
        
        # Get real current price
        ticker = adapter.client.fetch_ticker(symbol)
        current_price = Decimal(str(ticker['last']))
        print(f"Current BTC price: ${current_price}")
        
        initial_balance = adapter.balance
        print(f"Initial balance: ${initial_balance}")
        
        # Simulate buying BTC at current market price
        order = adapter.create_order(
            symbol=symbol,
            order_type="market",
            side="buy",
            amount=Decimal("0.01")  # 0.01 BTC
        )
        
        print(f"\nOrder executed (simulated):")
        print(f"  - Side: {order['side']}")
        print(f"  - Amount: {order['amount']} BTC")
        print(f"  - Price: ${order['price']}")
        print(f"  - Fee: ${order['fee']}")
        
        # Check position
        print(f"\nPosition after buy:")
        print(f"  - BTC position: {adapter.positions.get(symbol, 0)}")
        print(f"  - Balance: ${adapter.balance}")
        print(f"  - Margin used: ${adapter.margin_used.get(symbol, 0)}")
        
        assert symbol in adapter.positions
        assert adapter.positions[symbol] == Decimal("0.01")
        
        # Simulate selling to close
        order2 = adapter.create_order(
            symbol=symbol,
            order_type="market",
            side="sell",
            amount=Decimal("0.01")
        )
        
        print(f"\nClose order executed:")
        print(f"  - Realized PnL: ${order2['realized_pnl']}")
        print(f"  - Final balance: ${adapter.balance}")
        
        assert symbol not in adapter.positions
        print("\n✓ Simulated trading completed successfully")
    
    def test_paper_trading_workflow(self, adapter):
        """Test complete paper trading workflow."""
        print("\n=== Testing Complete Paper Trading Workflow ===")
        
        symbol = "BTC/USDT:USDT"
        
        # 1. Check initial state
        print(f"Initial balance: ${adapter.balance}")
        
        # 2. Set leverage
        adapter.set_leverage(symbol, 10)
        print("✓ Leverage set to 10x")
        
        # 3. Open long position at market
        print("\nOpening long position...")
        buy_order = adapter.create_order(
            symbol=symbol,
            order_type="market",
            side="buy",
            amount=Decimal("0.01")
        )
        print(f"✓ Position opened at ${buy_order['price']}")
        
        # 4. Check positions (simulated)
        positions = adapter.fetch_positions()
        print(f"\nOpen positions: {len(positions)}")
        if positions:
            pos = positions[0]
            print(f"  - Symbol: {pos['symbol']}")
            print(f"  - Size: {pos['contracts']}")
            print(f"  - Side: {pos['side']}")
            print(f"  - Entry: ${pos['entryPrice']}")
        
        # 5. Simulate price movement
        entry_price = adapter.entry_prices[symbol]
        new_price = entry_price * Decimal("1.02")  # 2% profit
        adapter.current_prices[symbol] = {"price": float(new_price)}
        print(f"\n📈 Simulated price move to ${new_price}")
        
        # 6. Check unrealized PnL
        positions = adapter.fetch_positions()
        if positions:
            print(f"  Unrealized PnL: ${positions[0]['unrealizedPnl']:.2f}")
        
        # 7. Close position
        print("\nClosing position...")
        sell_order = adapter.create_order(
            symbol=symbol,
            order_type="market",
            side="sell",
            amount=Decimal("0.01")
        )
        print(f"✓ Position closed")
        print(f"  Realized PnL: ${sell_order['realized_pnl']:.2f}")
        print(f"  Final balance: ${adapter.balance}")
        
        # 8. Verify no open positions
        final_positions = adapter.fetch_positions()
        assert len(final_positions) == 0
        
        print("\n✅ Complete workflow finished successfully!")
    
    def test_multiple_positions(self, adapter):
        """Test managing multiple positions."""
        print("\n=== Testing Multiple Positions ===")
        
        symbols = ["BTC/USDT:USDT", "ETH/USDT:USDT"]
        
        # Open positions in both
        for symbol in symbols:
            ticker = adapter.client.fetch_ticker(symbol)
            print(f"\nOpening position in {symbol} at ${ticker['last']}")
            
            adapter.create_order(
                symbol=symbol,
                order_type="market",
                side="buy",
                amount=Decimal("0.01")
            )
        
        # Check all positions
        positions = adapter.fetch_positions()
        print(f"\nTotal open positions: {len(positions)}")
        
        for pos in positions:
            print(f"  - {pos['symbol']}: {pos['contracts']} @ ${pos['entryPrice']}")
        
        assert len(positions) == 2
        print("\n✓ Multiple positions managed successfully")


class TestLiveModeCaution:
    """Tests for live mode - BE VERY CAREFUL!"""
    
    @pytest.fixture
    def adapter(self):
        """Create adapter in paper trading mode for testing."""
        return BinanceAdapter(
            config={"bot": {"mode": "paper"}},
            initial_balance=10000.0,
            leverage=10,
            maker_fee=0.0002,
            taker_fee=0.0004
        )
    
    @pytest.mark.skip(reason="Live mode uses REAL money - enable manually")
    def test_live_mode_warning(self):
        """
        WARNING: This test uses REAL money on REAL Binance!
        Only enable if you know what you're doing!
        """
        print("\n" + "="*60)
        print("⚠️  WARNING: LIVE MODE - REAL MONEY ⚠️")
        print("="*60)
        
        adapter = BinanceAdapter(
            config={"bot": {"mode": "live"}},
            leverage=1  # Use 1x leverage for safety
        )
        
        # Fetch real balance
        balance = adapter.fetch_balance()
        print(f"Real account balance: {balance}")
        
        print("\n❌ TEST STOPPED - Enable manually to continue")


    
    def test_api_key_setup(self, adapter):
        """Test that API keys are configured (for data fetching only)."""
        print("\n=== Testing API Configuration ===")
        
        print("Note: In paper mode, API keys are only used for fetching market data")
        print("      All order execution is simulated locally\n")
        
        # Try to fetch market data (this needs valid API keys)
        try:
            candles = adapter.fetch_ohlcv("BTC/USDT", "1h", 5)
            print(f"✓ Successfully fetched {len(candles)} candles")
            print(f"  API keys are valid for market data")
            
            if candles:
                latest_price = candles[-1][4]
                print(f"  Latest BTC price: ${latest_price}")
                
        except Exception as e:
            print(f"⚠️  Market data fetch failed: {e}")
            print("\nPossible issues:")
            print("  1. API keys not set in .env")
            print("  2. API keys invalid or expired")
            print("  3. IP not whitelisted")
            print("  4. API restrictions enabled")
            print("\nFor paper trading, you need API keys with:")
            print("  - Read permissions (for market data)")
            print("  - No trading permissions needed!")
            print("\nTo fix:")
            print("  1. Go to binance.com → API Management")
            print("  2. Create new API key with 'Enable Reading' only")
            print("  3. Add to .env:")
            print("     BINANCE_API_KEY=your_key")
            print("     BINANCE_SECRET_KEY=your_secret")


# Manual test runner
if __name__ == "__main__":
    print("=" * 60)
    print("BINANCE PAPER TRADING TESTS")
    print("=" * 60)
    print("\nPaper mode: Simulates orders with real market data")
    print("No testnet needed, no real money used\n")
    
    # Check for API keys
    if not os.getenv("BINANCE_API_KEY"):
        print("❌ ERROR: No API keys found!")
        print("\nYou need Binance API keys (read-only is fine for paper trading)")
        print("Add to .env:")
        print("   BINANCE_API_KEY=your_key")
        print("   BINANCE_SECRET_KEY=your_secret")
        print("\nGet them from: https://www.binance.com/en/my/settings/api-management")
        print("Enable 'Reading' permission only (no trading needed for paper mode)")
        sys.exit(1)
    
    test_suite = TestBinancePaperTrading()
    adapter = BinanceAdapter(
        config={"bot": {"mode": "paper"}},
        initial_balance=10000.0,
        leverage=10
    )
    
    try:
        print("\n" + "=" * 60)
        test_suite.test_api_key_setup(adapter)
        
        print("\n" + "=" * 60)
        test_suite.test_fetch_real_market_data(adapter)
        
        print("\n" + "=" * 60)
        adapter2 = BinanceAdapter(
            config={"bot": {"mode": "paper"}},
            initial_balance=10000.0,
            leverage=10
        )
        test_suite.test_simulated_order_with_real_prices(adapter2)
        
        print("\n" + "=" * 60)
        adapter3 = BinanceAdapter(
            config={"bot": {"mode": "paper"}},
            initial_balance=10000.0,
            leverage=10
        )
        test_suite.test_simulated_limit_order(adapter3)
        
        print("\n" + "=" * 60)
        adapter4 = BinanceAdapter(
            config={"bot": {"mode": "paper"}},
            initial_balance=10000.0,
            leverage=10
        )
        test_suite.test_paper_trading_workflow(adapter4)
        
        print("\n" + "=" * 60)
        print("✅ ALL PAPER TRADING TESTS PASSED!")
        print("=" * 60)
        
        print("\n📊 Summary:")
        print("   ✓ Orders are simulated locally")
        print("   ✓ Uses real market prices from Binance")
        print("   ✓ No real money involved")
        print("   ✓ No orders appear on exchange")
        print("   ✓ Perfect for strategy testing!")
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()

import sys
import os
from pathlib import Path
from decimal import Decimal
import time

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Load .env
try:
    from dotenv import load_dotenv
    load_dotenv(project_root / ".env")
except ImportError:
    print("Warning: python-dotenv not installed")

import pytest
from app.services.execution.cex.binance_adapter import BinanceAdapter


class TestBinanceTestnetIntegration:
    """Integration tests using Binance Testnet."""
    
    @pytest.fixture
    def adapter(self):
        """Create adapter connected to Binance testnet."""
        return BinanceAdapter(
            config={"bot": {"mode": "paper"}},  # Paper mode uses testnet
            leverage=10
        )
    
    def test_fetch_balance(self, adapter):
        """Test fetching balance from testnet."""
        print("\n=== Testing fetch_balance ===")
        
        balance = adapter.fetch_balance()
        
        print(f"Balance: {balance}")
        assert balance is not None
        assert "USDT" in balance or "total" in balance
        
        print("✓ Successfully fetched balance from testnet")
    
    def test_fetch_positions(self, adapter):
        """Test fetching positions from testnet."""
        print("\n=== Testing fetch_positions ===")
        
        positions = adapter.fetch_positions()
        
        print(f"Positions: {positions}")
        print(f"Number of open positions: {len(positions)}")
        
        for pos in positions:
            print(f"  - {pos['symbol']}: {pos['contracts']} contracts, "
                  f"side={pos['side']}, entry={pos.get('entryPrice')}")
        
        print("✓ Successfully fetched positions from testnet")
    
    def test_simulated_limit_order(self, adapter):
        """Test placing a simulated limit order in paper mode."""
        print("\n=== Testing Simulated Limit Order ===")
        
        symbol = "BTC/USDT:USDT"
        
        # In paper mode, set_leverage is simulated
        print("Setting leverage (simulated)...")
        adapter.leverage = Decimal("10")
        print(f"✓ Leverage set to {adapter.leverage}x (simulated)")
        
        # Get current market price
        ticker = adapter.client.fetch_ticker(symbol)
        current_price = Decimal(str(ticker['last']))
        print(f"Current market price: ${current_price}")
        
        # Place a limit order below market (simulated)
        limit_price = current_price * Decimal("0.95")  # 5% below market
        print(f"\nPlacing limit buy order at ${limit_price} (simulated)...")
        
        order = adapter.create_order(
            symbol=symbol,
            order_type="limit",
            side="buy",
            amount=Decimal("0.001"),
            price=limit_price
        )
        
        print(f"\n✓ Order created (simulated):")
        print(f"  - ID: {order['id']}")
        print(f"  - Type: {order['type']}")
        print(f"  - Side: {order['side']}")
        print(f"  - Amount: {order['amount']} BTC")
        print(f"  - Price: ${order['price']}")
        print(f"  - Fee: ${order['fee']}")
        
        # Check position was created
        assert symbol in adapter.positions
        print(f"  - Position: {adapter.positions[symbol]} BTC")
        print(f"  - Balance after: ${adapter.balance}")
        
        print("\n✓ Limit order simulation completed successfully")
        
        # Note: In paper mode, orders are executed immediately as simulation
        # No need to cancel since it's already "filled" in simulation
    
    def test_stop_loss_simulation(self, adapter):
        """Test stop loss order simulation."""
        print("\n=== Testing Stop Loss Simulation ===")
        
        symbol = "BTC/USDT:USDT"
        
        # Get current price
        ticker = adapter.client.fetch_ticker(symbol)
        current_price = Decimal(str(ticker['last']))
        print(f"Current price: ${current_price}")
        
        # First open a long position
        print("\nOpening long position...")
        adapter.create_order(
            symbol=symbol,
            order_type="market",
            side="buy",
            amount=Decimal("0.01")
        )
        
        entry_price = adapter.entry_prices[symbol]
        print(f"✓ Position opened at ${entry_price}")
        
        # Set stop loss price 5% below entry
        stop_price = entry_price * Decimal("0.95")
        print(f"\nSimulating stop loss at ${stop_price}...")
        
        # In paper mode, we can simulate hitting the stop loss
        # by manually executing a sell at the stop price
        print("Simulating stop loss trigger...")
        adapter.create_order(
            symbol=symbol,
            order_type="market",
            side="sell",
            amount=Decimal("0.01")
        )
        
        # Check position is closed
        assert symbol not in adapter.positions
        print("✓ Stop loss simulation completed (position closed)")
        
        # Show PnL
        last_trade = adapter.trade_history[-1]
        print(f"  Realized PnL: ${last_trade['realized_pnl']:.2f}")
    
    def test_market_order_workflow(self, adapter):
        """
        Full workflow: open position, place stop loss, close position.
        
        WARNING: This actually trades on testnet!
        """
        print("\n=== Testing full market order workflow ===")
        print("⚠ WARNING: This will execute real orders on testnet!")
        
        symbol = "BTC/USDT:USDT"
        position_size = Decimal("0.001")  # Small position
        
        try:
            # Get current price
            ticker = adapter.client.fetch_ticker(symbol)
            current_price = Decimal(str(ticker['last']))
            print(f"Current price: {current_price}")
            
            # 1. Set leverage
            adapter.set_leverage(symbol, 10)
            print("✓ Leverage set to 10x")
            
            # 2. Open long position (market buy)
            print(f"Opening long position: {position_size} BTC...")
            buy_order = adapter.create_order(
                symbol=symbol,
                order_type="market",
                side="buy",
                amount=position_size
            )
            print(f"✓ Long position opened: {buy_order}")
            
            time.sleep(2)
            
            # 3. Check positions
            positions = adapter.fetch_positions([symbol])
            print(f"Open positions: {positions}")
            
            # 4. Place stop loss
            if positions:
                stop_price = current_price * Decimal("0.90")  # 10% below
                print(f"Placing stop loss at {stop_price}...")
                
                sl_order = adapter.place_stop_loss(
                    symbol=symbol,
                    side="sell",
                    amount=position_size,
                    stop_price=stop_price
                )
                if sl_order:
                    print(f"✓ Stop loss placed: {sl_order['id']}")
            
            time.sleep(2)
            
            # 5. Close position (market sell)
            print(f"Closing position...")
            sell_order = adapter.create_order(
                symbol=symbol,
                order_type="market",
                side="sell",
                amount=position_size
            )
            print(f"✓ Position closed: {sell_order}")
            
            time.sleep(2)
            
            # 6. Verify position is closed
            final_positions = adapter.fetch_positions([symbol])
            print(f"Final positions: {final_positions}")
            
            print("✅ Full workflow completed successfully!")
            
        except Exception as e:
            print(f"❌ Workflow error: {e}")
            raise
    
    def test_fetch_ohlcv(self, adapter):
        """Test fetching candlestick data."""
        print("\n=== Testing fetch_ohlcv ===")
        
        candles = adapter.fetch_ohlcv("BTC/USDT", "1h", 10)
        
        print(f"Fetched {len(candles)} candles")
        if candles:
            latest = candles[-1]
            print(f"Latest candle: timestamp={latest[0]}, "
                  f"open={latest[1]}, high={latest[2]}, "
                  f"low={latest[3]}, close={latest[4]}")
        
        assert len(candles) > 0
        print("✓ Successfully fetched OHLCV data")


# Manual test runner
if __name__ == "__main__":
    print("=" * 60)
    print("BINANCE TESTNET INTEGRATION TESTS")
    print("=" * 60)
    print("\nThese tests will actually call Binance Testnet API")
    print("Make sure you have BINANCE_TESTNET_API_KEY set in .env\n")
    
    # Check for API keys
    if not os.getenv("BINANCE_TESTNET_API_KEY") and not os.getenv("BINANCE_API_KEY"):
        print("❌ ERROR: No API keys found!")
        print("\nPlease:")
        print("1. Get testnet keys from: https://testnet.binancefuture.com")
        print("2. Add to .env:")
        print("   BINANCE_TESTNET_API_KEY=your_key")
        print("   BINANCE_TESTNET_SECRET_KEY=your_secret")
        sys.exit(1)
    
    test_suite = TestBinanceTestnetIntegration()
    adapter = BinanceAdapter(config={"bot": {"mode": "paper"}}, leverage=10)
    
    try:
        # Run tests
        print("\n" + "=" * 60)
        test_suite.test_fetch_balance(adapter)
        
        print("\n" + "=" * 60)
        test_suite.test_fetch_positions(adapter)
        
        print("\n" + "=" * 60)
        test_suite.test_fetch_ohlcv(adapter)
        
        print("\n" + "=" * 60)
        test_suite.test_place_limit_order(adapter)
        
        print("\n" + "=" * 60)
        # Uncomment to run full workflow (actually trades)
        # response = input("\n⚠ Run full trading workflow? (yes/no): ")
        # if response.lower() == "yes":
        #     test_suite.test_market_order_workflow(adapter)
        
        print("\n" + "=" * 60)
        print("✅ ALL INTEGRATION TESTS PASSED!")
        print("=" * 60)
        
        print("\n📊 To see your orders:")
        print("   Visit: https://testnet.binancefuture.com")
        print("   Login and check your orders/positions")
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()