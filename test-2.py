import os
import sys
import time
from decimal import Decimal, ROUND_FLOOR
from pathlib import Path

# Add project root
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

# ==============================================================================
# HELPERS
# ==============================================================================

def banner(title: str):
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)

def smart_round(value: Decimal, precision: int) -> Decimal:
    """Rounds value to the specific precision required by the exchange."""
    if precision == 0:
        return value.quantize(Decimal("1"), rounding=ROUND_FLOOR)
    
    quantizer = Decimal("1") / Decimal(str(10**precision))
    return value.quantize(quantizer, rounding=ROUND_FLOOR)

def get_ccxt_timeframe(tf_str: str) -> str:
    tf_map = {'D1': '1d', 'H4': '4h', 'H1': '1h', 'M15': '15m', 'M1': '1m'}
    return tf_map.get(tf_str, tf_str.lower())

# ==============================================================================
# STRATEGY 1: MULTI TP (Limit Orders + 0.5R Logic)
# ==============================================================================

def monitor_multi_tp_strategy(adapter: BinanceAdapter, symbol: str, entry_price: Decimal, initial_sl: Decimal, 
                              entry_side: str, tp_orders: list, timeframe: str, total_qty: Decimal):
    """
    Monitors 2 Limit TPs + 0.5R Dynamic SL.
    On SIGINT: Closes Position & Cancels TPs.
    """
    r_dist = abs(entry_price - initial_sl)
    
    if entry_side == "buy":
        trigger_05r = entry_price + (r_dist * Decimal("0.5"))
        new_sl_02r  = entry_price + (r_dist * Decimal("0.2"))
    else:
        trigger_05r = entry_price - (r_dist * Decimal("0.5"))
        new_sl_02r  = entry_price - (r_dist * Decimal("0.2"))

    current_sl = initial_sl
    sl_moved = False
    
    banner(f"MULTI TP MONITOR")
    print(f"   Entry: {entry_price} | SL: {initial_sl} | R: {r_dist}")
    print(f"   0.5R Trigger: {trigger_05r} -> Move SL to {new_sl_02r}")
    print("   Press Ctrl+C to Force Close Position")

    ccxt_tf = get_ccxt_timeframe(timeframe)
    exit_side = "sell" if entry_side == "buy" else "buy"

    # Track open TPs to cancel them if needed
    open_tp_ids = list(tp_orders)

    while True:
        try:
            # 1. POSITION CHECK (Using Adapter Method)
            if not adapter.check_position_active(symbol):
                print("\nPosition removed/liquidated. Stopping bot.")
                for oid in tp_orders:
                    adapter.cancel_order(oid, symbol)
                break

            # 2. CHECK TP ORDERS
            current_open_tps = []
            for oid in tp_orders:
                try:
                    # Direct call to adapter
                    o = adapter.fetch_order(oid, symbol)
                    if o['status'] not in ['filled', 'closed', 'canceled']:
                        current_open_tps.append(oid)
                except:
                    current_open_tps.append(oid)
            
            open_tp_ids = current_open_tps

            if not open_tp_ids:
                print("\nALL TPs FILLED. Trade Closed.")
                break

            # 3. GET DATA
            ohlcv = adapter.fetch_ohlcv(symbol, timeframe=ccxt_tf, limit=2)
            ticker = adapter.fetch_ticker(symbol)
            if not ohlcv: continue
            
            last_close = Decimal(str(ohlcv[-2][4]))
            current_price = Decimal(str(ticker['last']))

            # 4. DYNAMIC SL TRIGGER (0.5R)
            if not sl_moved:
                if (entry_side == "buy" and current_price >= trigger_05r) or \
                   (entry_side == "sell" and current_price <= trigger_05r):
                    current_sl = new_sl_02r
                    sl_moved = True
                    print(f"\nHIT 0.5R! Soft SL moved to 0.2R ({new_sl_02r})")

            # 5. CHECK SL HIT
            sl_hit = False
            if entry_side == "buy" and last_close < current_sl: sl_hit = True
            elif entry_side == "sell" and last_close > current_sl: sl_hit = True

            if sl_hit:
                print(f"\nSL HIT (Close: {last_close}). Exiting...")
                for oid in open_tp_ids:
                    adapter.cancel_order(oid, symbol)
                
                adapter.create_order(symbol, "market", exit_side, total_qty)
                break

            sys.stdout.write(f"\rPrice: {current_price} | SL: {current_sl} | Open TPs: {len(open_tp_ids)}  ")
            sys.stdout.flush()
            time.sleep(3)

        except KeyboardInterrupt:
            print("\n\nSIGINT RECEIVED (Manual Stop).")
            print("   1. Canceling Open TPs...")
            for oid in open_tp_ids:
                adapter.cancel_order(oid, symbol)
                print(f"      -> Canceled {oid}")
            
            print(f"   2. Closing Position (Market {exit_side.upper()})...")
            adapter.create_order(symbol, "market", exit_side, total_qty)
            print("      Position Closed.")
            break

        except Exception:
            time.sleep(3)

# ==============================================================================
# STRATEGY 2: SINGLE TP (Limit Order)
# ==============================================================================

def monitor_single_tp_strategy(adapter: BinanceAdapter, symbol: str, entry_side: str, sl_price: Decimal, 
                               tp_order_id: str, timeframe: str, total_qty: Decimal):
    """
    Monitors Single Limit TP with Hybrid SL (Hard + Soft).
    """
    banner(f"SINGLE TP MONITOR (HYBRID SL)")
    print(f"   Soft SL (Candle Close): {sl_price}")
    print(f"   Hard SL (Live Price):   {sl_price} (Immediate)")
    print("   Press Ctrl+C to Force Close Position")
    
    ccxt_tf = get_ccxt_timeframe(timeframe)
    exit_side = "sell" if entry_side == "buy" else "buy"

    while True:
        try:
            # 1. POSITION CHECK
            if not adapter.check_position_active(symbol):
                print("\nPosition removed/liquidated. Stopping bot.")
                adapter.cancel_order(tp_order_id, symbol)
                break

            # 2. CHECK TP ORDER
            try:
                o = adapter.fetch_order(tp_order_id, symbol)
                status = o.get('status')
                if status in ['filled', 'closed']:
                    print("\nTP FILLED. Trade Closed.")
                    break
                elif status == 'canceled':
                    print("\nTP Canceled manually.")
            except:
                pass 

            # 3. CHECK LIVE PRICE (HARD SL)
            ticker = adapter.fetch_ticker(symbol)
            current_price = Decimal(str(ticker['last']))

            if (entry_side == "buy" and current_price <= sl_price) or \
               (entry_side == "sell" and current_price >= sl_price):
                print(f"\nHARD SL HIT (Live: {current_price}). Exiting...")
                adapter.cancel_order(tp_order_id, symbol)
                adapter.create_order(symbol, "market", exit_side, total_qty)
                break

            # 4. CHECK CANDLE CLOSE (SOFT SL)
            ohlcv = adapter.fetch_ohlcv(symbol, timeframe=ccxt_tf, limit=2)
            if ohlcv:
                last_close = Decimal(str(ohlcv[-2][4]))
                
                sl_hit = False
                if entry_side == "buy" and last_close < sl_price: sl_hit = True
                elif entry_side == "sell" and last_close > sl_price: sl_hit = True

                if sl_hit:
                    print(f"\nSOFT SL HIT (Close: {last_close}). Exiting...")
                    adapter.cancel_order(tp_order_id, symbol)
                    adapter.create_order(symbol, "market", exit_side, total_qty)
                    break

            sys.stdout.write(f"\rPrice: {current_price} | SL: {sl_price}  ")
            sys.stdout.flush()
            time.sleep(1)

        except KeyboardInterrupt:
            print("\n\nSIGINT RECEIVED (Manual Stop).")
            adapter.cancel_order(tp_order_id, symbol)
            print(f"   -> Canceled TP {tp_order_id}")
            
            adapter.create_order(symbol, "market", exit_side, total_qty)
            print("   -> Position Closed.")
            break
            
        except Exception:
            time.sleep(1)

# ==============================================================================
# EXECUTION CONTROLLER
# ==============================================================================

def execute_bot_signal(adapter: BinanceAdapter, signal_data: dict, usdt_amount: Decimal):
    """
    Accepts USDT Amount, calculates Quantity using dynamic precision.
    """
    raw_symbol = signal_data.get("Symbol", "BTCUSDT")
    
    # [1] FETCH DYNAMIC PRECISION (Using new Adapter method)
    price_prec, qty_prec = adapter.get_precision_info(raw_symbol)

    direction = signal_data.get("Side", "").lower()
    entry_side = "sell" if ("sell" in direction or "short" in direction) else "buy"
    exit_side = "buy" if entry_side == "sell" else "sell"
    
    # [2] CALCULATE QUANTITY
    ticker = adapter.fetch_ticker(raw_symbol) 
    entry_price = smart_round(Decimal(str(ticker['last'])), price_prec)
    
    # Volume = USDT / Price
    raw_qty = usdt_amount / entry_price
    total_qty = smart_round(raw_qty, qty_prec)
    
    # Handle SL
    raw_sl = Decimal(str(signal_data.get("SL")))
    sl_price = smart_round(raw_sl, price_prec)

    print(f"\nENTRY {entry_side.upper()} @ Market ({entry_price}) | Vol: {total_qty}")
    entry_order = adapter.create_order(raw_symbol, "market", entry_side, total_qty)
    
    if entry_order.get('status') == 'failed':
        print(f"Entry Failed: {entry_order}")
        return

    # --- DETECT TP TYPE ---
    tp_keys = [k for k in signal_data.keys() if k.startswith("TP")]
    is_multi_tp = len(tp_keys) > 1 or "TP 1" in signal_data
    
    if is_multi_tp:
        # === MULTI TP ===
        print(f"\nDETECTED MULTI-TP. Placing Limit Orders (50/50).")
        
        targets = []
        if "TP 1" in signal_data: targets.append(Decimal(str(signal_data["TP 1"])))
        if "TP 2" in signal_data: targets.append(Decimal(str(signal_data["TP 2"])))
        
        qty_per_tp = smart_round(total_qty / len(targets), qty_prec)
        qty_sum = qty_per_tp * (len(targets) - 1)
        last_qty = total_qty - qty_sum

        tp_ids = []
        for i, target in enumerate(targets):
            final_price = smart_round(target, price_prec)
            this_qty = last_qty if i == len(targets) - 1 else qty_per_tp

            print(f"   -> Placing Limit TP {i+1} @ {final_price} (Qty: {this_qty})")
            o = adapter.create_order(raw_symbol, "limit", exit_side, this_qty, final_price)
            if o.get('id'): tp_ids.append(o.get('id'))

        monitor_multi_tp_strategy(adapter, raw_symbol, entry_price, sl_price, entry_side, tp_ids, signal_data.get("Timeframe", "M1"), total_qty)

    else:
        # === SINGLE TP ===
        print(f"\nDETECTED SINGLE TP. Placing Limit Order.")
        
        raw_tp = signal_data.get("TP") or signal_data.get("TP 1") 
        tp_price = smart_round(Decimal(str(raw_tp)), price_prec)
        
        print(f"   -> Placing Limit TP @ {tp_price}")
        tp_order = adapter.create_order(raw_symbol, "limit", exit_side, total_qty, tp_price)
        
        if tp_order and tp_order.get('id'):
            monitor_single_tp_strategy(adapter, raw_symbol, entry_side, sl_price, tp_order.get('id'), signal_data.get("Timeframe", "M1"), total_qty)
        else:
            print(f"Failed to place TP: {tp_order.get('error')}")

# ==============================================================================
# MAIN
# ==============================================================================

def main():
    banner("BINANCE ADAPTER TEST")
    
    if not os.getenv("BINANCE_API_KEY"):
        print("Error: Env vars missing.")
        return

    # 1. Initialize Adapter (Defaults to PAPER mode)
    adapter = BinanceAdapter(
        config={"bot": {"mode": "paper"}}, 
        initial_balance=1000.0,
    )
    
    # 2. Switch to Live Mode instantly if needed (uncomment below)
    # adapter.mode = "live" 

    print(f"Current Mode: {adapter.mode.upper()}")

    raw_symbol = "BTCUSDT" # or "BTCUSDT"
    
    try:
        # Fetch current price
        ticker = adapter.fetch_ticker(raw_symbol)
        price = Decimal(str(ticker['last']))
        
        print(f"Current Price ({raw_symbol}): {price}")

        # Scenario A: Multi TP
        sig_multi = {
            "Symbol": raw_symbol,
            "Side": "Buy",
            "SL": float(price * Decimal("0.98")),      
            "TP 1": float(price * Decimal("1.02")),     
            "TP 2": float(price * Decimal("1.04")),     
            "Timeframe": "M1"
        }
        
        # Scenario B: Single TP
        sig_single = {
            "Symbol": raw_symbol,
            "Side": "Buy",
            "SL": float(price * Decimal("1.0")),       
            "TP": float(price * Decimal("1.03")),       
            "Timeframe": "M1"
        }
        
        # --- EXECUTE ---
        print("\n>>> EXECUTION: Testing Single TP Signal")
        execute_bot_signal(adapter, sig_single, usdt_amount=Decimal("500"))

    except Exception as e:
        print(f"Main Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()