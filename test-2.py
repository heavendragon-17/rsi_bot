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

def smart_round(value: Decimal, precision: int = 1) -> Decimal:
    """Round to exchange precision."""
    quantizer = Decimal("1") / Decimal(str(10**precision))
    return value.quantize(quantizer, rounding=ROUND_FLOOR)

def get_ccxt_timeframe(tf_str: str) -> str:
    tf_map = {'D1': '1d', 'H4': '4h', 'H1': '1h', 'M15': '15m', 'M1': '1m'}
    return tf_map.get(tf_str, tf_str.lower())

def check_position_active(adapter, symbol: str) -> bool:
    """
    Returns True if position exists and size > 0.
    """
    try:
        positions = adapter.fetch_positions([symbol])
        target_clean = symbol.replace('/', '').split(':')[0]
        
        for p in positions:
            p_sym_clean = p['symbol'].replace('/', '').split(':')[0]
            if p_sym_clean == target_clean:
                if float(p.get('contracts', 0)) > 0:
                    return True
        return False
    except Exception as e:
        print(f"Error checking position: {e}")
        return True 

# ==============================================================================
# STRATEGY 1: MULTI TP
# ==============================================================================

def monitor_multi_tp_strategy(adapter, symbol: str, entry_price: Decimal, initial_sl: Decimal, 
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
            # 1. POSITION CHECK
            if not check_position_active(adapter, symbol):
                print("\nPosition removed/liquidated. Stopping bot.")
                for oid in tp_orders:
                    try: adapter.client.cancel_order(oid, symbol)
                    except: pass
                break

            # 2. CHECK TP ORDERS
            current_open_tps = []
            for oid in tp_orders:
                try:
                    o = adapter.client.fetch_order(oid, symbol)
                    if o['status'] not in ['filled', 'closed', 'canceled']:
                        current_open_tps.append(oid)
                except:
                    current_open_tps.append(oid)
            
            open_tp_ids = current_open_tps

            if not open_tp_ids:
                print("\nALL TPs FILLED. Trade Closed.")
                break

            # 3. GET DATA
            ohlcv = adapter.client.fetch_ohlcv(symbol, timeframe=ccxt_tf, limit=2)
            ticker = adapter.client.fetch_ticker(symbol)
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
                    try: adapter.client.cancel_order(oid, symbol)
                    except: pass
                
                adapter.create_order(symbol, "market", exit_side, total_qty)
                break

            sys.stdout.write(f"\rPrice: {current_price} | SL: {current_sl} | Open TPs: {len(open_tp_ids)}  ")
            sys.stdout.flush()
            time.sleep(3)

        except KeyboardInterrupt:
            print("\n\nSIGINT RECEIVED (Manual Stop).")
            print("   1. Canceling Open TPs...")
            for oid in open_tp_ids:
                try: 
                    adapter.client.cancel_order(oid, symbol)
                    print(f"      -> Canceled {oid}")
                except Exception as e: 
                    print(f"      -> Failed {oid}: {e}")
            
            print(f"   2. Closing Position (Market {exit_side.upper()})...")
            try:
                adapter.create_order(symbol, "market", exit_side, total_qty)
                print("      Position Closed.")
            except Exception as e:
                print(f"      Close Failed: {e}")
            break

        except Exception:
            time.sleep(3)

# ==============================================================================
# STRATEGY 2: SINGLE TP
# ==============================================================================

def monitor_single_tp_strategy(adapter, symbol: str, entry_side: str, sl_price: Decimal, 
                               tp_order_id: str, timeframe: str, total_qty: Decimal):
    """
    Monitors Single Limit TP.
    On SIGINT: Closes Position & Cancels TP.
    """
    banner(f"SINGLE TP MONITOR")
    print(f"   SL Trigger: Candle Close beyond {sl_price}")
    print("   Press Ctrl+C to Force Close Position")
    
    ccxt_tf = get_ccxt_timeframe(timeframe)
    exit_side = "sell" if entry_side == "buy" else "buy"

    while True:
        try:
            # 1. POSITION CHECK
            if not check_position_active(adapter, symbol):
                print("\nPosition removed/liquidated. Stopping bot.")
                try: adapter.client.cancel_order(tp_order_id, symbol)
                except: pass
                break

            # 2. CHECK TP ORDER
            try:
                o = adapter.client.fetch_order(tp_order_id, symbol)
                status = o.get('status')
                if status in ['filled', 'closed']:
                    print("\nTP FILLED. Trade Closed.")
                    break
                elif status == 'canceled':
                    print("\nTP Canceled manually.")
            except:
                pass 

            # 3. CHECK SL HIT
            ohlcv = adapter.client.fetch_ohlcv(symbol, timeframe=ccxt_tf, limit=2)
            if not ohlcv: continue
            last_close = Decimal(str(ohlcv[-2][4]))
            
            sl_hit = False
            if entry_side == "buy" and last_close < sl_price: sl_hit = True
            elif entry_side == "sell" and last_close > sl_price: sl_hit = True

            if sl_hit:
                print(f"\nSL HIT (Close: {last_close}). Exiting...")
                try: adapter.client.cancel_order(tp_order_id, symbol)
                except: pass
                
                adapter.create_order(symbol, "market", exit_side, total_qty)
                break

            sys.stdout.write(f"\rMonitor running... Close: {last_close} vs SL: {sl_price}  ")
            sys.stdout.flush()
            time.sleep(3)

        except KeyboardInterrupt:
            print("\n\nSIGINT RECEIVED (Manual Stop).")
            print("   1. Canceling TP Order...")
            try: 
                adapter.client.cancel_order(tp_order_id, symbol)
                print(f"      -> Canceled {tp_order_id}")
            except: pass
            
            print(f"   2. Closing Position (Market {exit_side.upper()})...")
            try:
                adapter.create_order(symbol, "market", exit_side, total_qty)
                print("      Position Closed.")
            except Exception as e:
                print(f"      Close Failed: {e}")
            break
            
        except Exception:
            time.sleep(3)

# ==============================================================================
# EXECUTION CONTROLLER
# ==============================================================================

def execute_bot_signal(adapter, signal_data: dict, total_qty: Decimal):
    """
    Main entry point. Places Entry + Limit TPs.
    """
    raw_symbol = signal_data.get("Symbol", "BTCUSDT")
    symbol = f"{raw_symbol[:-4]}/USDT:USDT" if (raw_symbol.endswith("USDT") and ":" not in raw_symbol) else raw_symbol
    
    direction = signal_data.get("Side", "").lower()
    entry_side = "sell" if ("sell" in direction or "short" in direction) else "buy"
    exit_side = "buy" if entry_side == "sell" else "sell"
    
    # Prices
    ticker = adapter.client.fetch_ticker(symbol)
    entry_price = smart_round(Decimal(str(ticker['last'])))
    raw_sl = Decimal(str(signal_data.get("SL")))
    sl_price = smart_round(raw_sl)

    print(f"\nENTRY {entry_side.upper()} @ Market ({entry_price})")
    entry_order = adapter.create_order(symbol, "market", entry_side, total_qty)
    
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
        
        qty_per_tp = smart_round(total_qty / len(targets), 3)
        tp_ids = []

        for i, target in enumerate(targets):
            final_price = smart_round(target, 1) 
            print(f"   -> Placing Limit TP {i+1} @ {final_price} (Qty: {qty_per_tp})")
            o = adapter.create_order(symbol, "limit", exit_side, qty_per_tp, final_price)
            if o.get('id'): tp_ids.append(o.get('id'))

        monitor_multi_tp_strategy(adapter, symbol, entry_price, sl_price, entry_side, tp_ids, signal_data.get("Timeframe", "M1"), total_qty)

    else:
        # === SINGLE TP ===
        print(f"\nDETECTED SINGLE TP. Placing Limit Order.")
        
        raw_tp = signal_data.get("TP") or signal_data.get("TP 1") 
        tp_price = smart_round(Decimal(str(raw_tp)), 1)
        
        print(f"   -> Placing Limit TP @ {tp_price}")
        tp_order = adapter.create_order(symbol, "limit", exit_side, total_qty, tp_price)
        
        if tp_order and tp_order.get('id'):
            monitor_single_tp_strategy(adapter, symbol, entry_side, sl_price, tp_order.get('id'), signal_data.get("Timeframe", "M1"), total_qty)
        else:
            print(f"Failed to place TP: {tp_order.get('error')}")

# ==============================================================================
# MAIN
# ==============================================================================

def main():
    banner("BINANCE AUTO STRATEGY TEST")
    
    if not os.getenv("BINANCE_API_KEY"):
        print("Error: Env vars missing.")
        return

    adapter = BinanceAdapter(
        config={"bot": {"mode": "paper"}}, 
        initial_balance=1000.0,
    )

    ticker = adapter.client.fetch_ticker("BTC/USDT:USDT")
    price = Decimal(str(ticker['last']))
    sl_price = price * Decimal("0.998") 

    # --- SINGLE TP TEST CASE ---
    sig_single = {
        "Symbol": "BTCUSDT",
        "Side": "Buy",
        "SL": float(sl_price),
        "TP": float(price * Decimal("1.01")),
        "Timeframe": "M1"
    }

    # --- MULTI TP TEST CASE ---
    sig_multi = {
        "Symbol": "BTCUSDT",
        "Side": "Buy",
        "SL": float(sl_price),
        "TP 1": float(price * Decimal("1.002")), # 1R (approx)
        "TP 2": float(price * Decimal("1.004")), # 2R
        "Timeframe": "M1"
    }
    
    # Running both tests sequentially
    execute_bot_signal(adapter, sig_single, Decimal("0.005"))
    # execute_bot_signal(adapter, sig_multi, Decimal("0.006"))

if __name__ == "__main__":
    main()