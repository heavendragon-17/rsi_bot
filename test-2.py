import os
import sys
import time
import math
from decimal import Decimal, ROUND_FLOOR
from pathlib import Path

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

def smart_round(value: Decimal, precision: int = 1) -> Decimal:
    """
    Làm tròn giá trị về số lượng chữ số thập phân cho phép.
    Ví dụ: BTCUSDT tick_size=0.1 -> precision=1
    """
    # Lấy lượng lượng tử (quantizer) ví dụ: 0.1
    quantizer = Decimal("1") / Decimal(str(10**precision))
    return value.quantize(quantizer, rounding=ROUND_FLOOR)

def place_market_order_from_signal(adapter, signal_data: dict, total_qty: Decimal):
    banner("EXECUTING BOT SIGNAL")

    # --- 1. XỬ LÝ DỮ LIỆU TÍN HIỆU ---
    raw_symbol = signal_data.get("Symbol", "BTCUSDT")
    
    if raw_symbol.endswith("USDT") and ":" not in raw_symbol:
        symbol = f"{raw_symbol[:-4]}/USDT:USDT"
    else:
        symbol = raw_symbol

    # Side
    direction = signal_data.get("Side", "").lower()
    entry_side = "sell" if ("sell" in direction or "short" in direction) else "buy"
    exit_side = "buy" if entry_side == "sell" else "sell"

    # === QUAN TRỌNG: Cấu hình Precision (Độ chính xác) cho BTCUSDT ===
    # Trên thực tế, Adapter nên tự động fetch exchange info để lấy số này.
    # Với BTCUSDT Futures, thường là: Price Precision = 1 (0.1), Qty Precision = 3 (0.001)
    PRICE_PRECISION = 1 
    
    # Lấy giá SL và làm tròn
    raw_sl = Decimal(str(signal_data.get("SL", 0)))
    sl_price = smart_round(raw_sl, PRICE_PRECISION)
    
    # Lấy danh sách TP và làm tròn
    tp_targets = []
    for key in ["TP 1", "TP 2", "TP 3"]:
        if key in signal_data:
            raw_tp = Decimal(str(signal_data[key]))
            tp_targets.append(smart_round(raw_tp, PRICE_PRECISION))

    # Log thông tin
    tf = signal_data.get("Timeframe", "Unknown")
    print(f"🔹 Signal: {entry_side.upper()} {symbol} [{tf}] | Vol: {total_qty}")
    print(f"🔹 SL (Rounded): {sl_price} (Gốc: {raw_sl})")
    print(f"🔹 TP (Rounded): {tp_targets}")

    # --- 2. VÀO LỆNH ENTRY (MARKET) ---
    print(f"\n➤ 1. Placing ENTRY ({entry_side.upper()} - MARKET)...")
    entry_order = adapter.create_order(
        symbol=symbol,
        order_type="market",
        side=entry_side,
        amount=total_qty
    )
    
    if entry_order.get('status') == 'failed':
        print(f"❌ Entry failed: {entry_order.get('error')}")
        return

    print(f"✅ Entry Filled! ID: {entry_order.get('id')}")
    time.sleep(2)

    # --- 3. ĐẶT STOP LOSS (STOP_MARKET) ---
    print(f"\n➤ 2. Placing SL ({exit_side.upper()} - STOP_MARKET) @ {sl_price}...")
    sl_order = adapter.place_stop_loss(
        symbol=symbol,
        side=exit_side,
        amount=total_qty,
        stop_price=sl_price
    )
    if sl_order:
        print(f"✅ SL Placed. ID: {sl_order.get('id')}")
    else:
        print("❌ Failed to place SL")

    # --- 4. ĐẶT TAKE PROFIT (LIMIT) ---
    if tp_targets:
        qty_per_tp = total_qty / len(tp_targets)
        # Làm tròn volume TP (BTC cho phép 3 số thập phân, ví dụ 0.005)
        qty_per_tp = smart_round(qty_per_tp, 3) 

        print(f"\n➤ 3. Placing TPs ({exit_side.upper()} - LIMIT)...")
        for i, tp_price in enumerate(tp_targets, 1):
            print(f"   ➜ TP {i} @ {tp_price} (Qty: {qty_per_tp})")
            
            tp_order = adapter.create_order(
                symbol=symbol,
                order_type="limit",
                side=exit_side,
                amount=qty_per_tp,
                price=tp_price
            )
            
            if tp_order.get('status') != 'failed':
                print(f"     ✅ TP {i} Placed. ID: {tp_order.get('id')}")
            else:
                print(f"     ❌ TP {i} Failed: {tp_order.get('error')}")

    print("\n" + "=" * 30)
    print("✅ SIGNAL EXECUTION COMPLETE")
    print("=" * 30)


def main():
    banner("BINANCE ADAPTER - TESTNET SIGNAL TEST")

    if not (os.getenv("BINANCE_API_KEY") or os.getenv("BINANCE_TESTNET_API_KEY")):
        print("ERROR: Missing BINANCE_API_KEY / SECRET in .env")
        return

    adapter = BinanceAdapter(
        config={"bot": {"mode": "paper"}},
        initial_balance=1000.0,
        leverage=20,
    )

    bot_signal = {
        "Symbol": "BTCUSDT",
        "Timeframe": "15m",
        "Side": "Sell",
        "Entry": 91075.9225, 
        "TP 1": 89471.4475,
        "TP 2": 88669.21,
        "TP 3": 87385.63,
        "SL": 92840.845
    }

    try:
        # Volum 0.015 chia cho 3 TP = 0.005 (đẹp)
        place_market_order_from_signal(adapter, bot_signal, Decimal("0.015"))
        
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()