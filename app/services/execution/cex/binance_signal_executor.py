import time
import sys
from decimal import Decimal, ROUND_FLOOR
from typing import List, Optional

class BinanceSignalExecutor:
    """
    Handles signal execution logic (Entry, SL, TP) using a BinanceAdapter.
    Supports:
    1. Single TP (Limit) + Hybrid SL (Hard + Soft)
    2. Multi TP (Limit) + Dynamic Trailing SL (0.5R -> 0.2R)
    3. Auto-calculation of Quantity from USDT Amount
    4. Dynamic Precision handling
    """

    def __init__(self, adapter):
        self.adapter = adapter

    # ==========================================================================
    # PUBLIC INTERFACE
    # ==========================================================================

    def execute(self, signal_data: dict, usdt_amount: Decimal):
        """
        Main entry point.
        1. Fetches precision & price.
        2. Calculates volume from USDT.
        3. Places Entry Market Order.
        4. Detects Strategy (Single/Multi) and places TPs.
        5. Starts Monitoring Loop.
        """
        raw_symbol = signal_data.get("Symbol", "BTCUSDT")
        
        # 1. Fetch Precision & Price
        price_prec, qty_prec = self.adapter.get_precision_info(raw_symbol)
        ticker = self.adapter.fetch_ticker(raw_symbol)
        current_price = self._smart_round(Decimal(str(ticker['last'])), price_prec)

        # 2. Calculate Quantity
        # Vol = USDT / Price
        raw_qty = usdt_amount / current_price
        total_qty = self._smart_round(raw_qty, qty_prec)

        # 3. Parse Signal
        direction = signal_data.get("Side", "").lower()
        entry_side = "sell" if ("sell" in direction or "short" in direction) else "buy"
        exit_side = "buy" if entry_side == "sell" else "sell"
        
        raw_sl = Decimal(str(signal_data.get("SL")))
        sl_price = self._smart_round(raw_sl, price_prec)

        # 4. Execute Entry
        print(f"\n[EXECUTOR] ENTRY {entry_side.upper()} @ Market ({current_price}) | Vol: {total_qty}")
        entry_order = self.adapter.create_order(raw_symbol, "market", entry_side, total_qty)

        if entry_order.get('status') == 'failed':
            print(f"Entry Failed: {entry_order}")
            return

        # 5. Route to Strategy
        tp_keys = [k for k in signal_data.keys() if k.startswith("TP")]
        is_multi_tp = len(tp_keys) > 1 or "TP 1" in signal_data

        if is_multi_tp:
            self._handle_multi_tp(raw_symbol, signal_data, entry_side, exit_side, 
                                  entry_price=current_price, sl_price=sl_price, 
                                  total_qty=total_qty, price_prec=price_prec, qty_prec=qty_prec)
        else:
            self._handle_single_tp(raw_symbol, signal_data, entry_side, exit_side, 
                                   sl_price=sl_price, total_qty=total_qty, 
                                   price_prec=price_prec)

    # ==========================================================================
    # STRATEGY HANDLERS
    # ==========================================================================

    def _handle_multi_tp(self, symbol, signal, entry_side, exit_side, entry_price, sl_price, total_qty, price_prec, qty_prec):
        print(f"[EXECUTOR] Strategy: MULTI-TP (Dynamic Trailing)")
        
        # Parse Targets
        targets = []
        if "TP 1" in signal: targets.append(Decimal(str(signal["TP 1"])))
        if "TP 2" in signal: targets.append(Decimal(str(signal["TP 2"])))
        
        # Calculate Split Volume
        qty_per_tp = self._smart_round(total_qty / len(targets), qty_prec)
        qty_sum = qty_per_tp * (len(targets) - 1)
        last_qty = total_qty - qty_sum

        # Place Limit Orders
        tp_ids = []
        for i, target in enumerate(targets):
            final_price = self._smart_round(target, price_prec)
            this_qty = last_qty if i == len(targets) - 1 else qty_per_tp
            
            print(f"   -> Placing TP {i+1} @ {final_price} (Qty: {this_qty})")
            o = self.adapter.create_order(symbol, "limit", exit_side, this_qty, final_price)
            if o.get('id'): tp_ids.append(o.get('id'))

        # Start Monitor
        self._monitor_multi_tp(symbol, entry_price, sl_price, entry_side, exit_side, tp_ids, 
                               signal.get("Timeframe", "M1"), total_qty)

    def _handle_single_tp(self, symbol, signal, entry_side, exit_side, sl_price, total_qty, price_prec):
        print(f"[EXECUTOR] Strategy: SINGLE-TP (Hybrid SL)")
        
        raw_tp = signal.get("TP") or signal.get("TP 1")
        tp_price = self._smart_round(Decimal(str(raw_tp)), price_prec)

        print(f"   -> Placing TP @ {tp_price}")
        tp_order = self.adapter.create_order(symbol, "limit", exit_side, total_qty, tp_price)

        if tp_order and tp_order.get('id'):
            self._monitor_single_tp(symbol, entry_side, exit_side, sl_price, 
                                    tp_order.get('id'), signal.get("Timeframe", "M1"), total_qty)
        else:
            print(f"Failed to place TP: {tp_order.get('error')}")

    # ==========================================================================
    # MONITORING LOOPS
    # ==========================================================================

    def _monitor_multi_tp(self, symbol, entry_price, initial_sl, entry_side, exit_side, tp_orders, timeframe, total_qty):
        # Calculate R Distances for Trailing
        r_dist = abs(entry_price - initial_sl)
        if entry_side == "buy":
            trigger_05r = entry_price + (r_dist * Decimal("0.5"))
            new_sl_02r  = entry_price + (r_dist * Decimal("0.2"))
        else:
            trigger_05r = entry_price - (r_dist * Decimal("0.5"))
            new_sl_02r  = entry_price - (r_dist * Decimal("0.2"))

        current_sl = initial_sl
        sl_moved = False
        ccxt_tf = self._get_ccxt_timeframe(timeframe)
        open_tp_ids = list(tp_orders)

        print(f"   [MONITOR] Started. 0.5R Trigger: {trigger_05r} -> Move SL to {new_sl_02r}")

        while True:
            try:
                # 1. Position Check
                if not self.adapter.check_position_active(symbol):
                    print("\n[STOP] Position closed/liquidated.")
                    for oid in tp_orders: self.adapter.cancel_order(oid, symbol)
                    break

                # 2. Check TPs
                open_tp_ids = [oid for oid in tp_orders if self._is_order_open(oid, symbol)]
                if not open_tp_ids:
                    print("\n[WIN] All TPs Filled.")
                    break

                # 3. Get Data
                ticker = self.adapter.fetch_ticker(symbol)
                current_price = Decimal(str(ticker['last']))
                ohlcv = self.adapter.fetch_ohlcv(symbol, timeframe=ccxt_tf, limit=2)
                
                # 4. Dynamic Trailing (0.5R)
                if not sl_moved:
                    if (entry_side == "buy" and current_price >= trigger_05r) or \
                       (entry_side == "sell" and current_price <= trigger_05r):
                        current_sl = new_sl_02r
                        sl_moved = True
                        print(f"\n[TRAIL] Hit 0.5R! SL moved to {new_sl_02r} (Locked Profit)")

                # 5. Check SL (Candle Close)
                if ohlcv:
                    last_close = Decimal(str(ohlcv[-2][4]))
                    sl_hit = (entry_side == "buy" and last_close < current_sl) or \
                             (entry_side == "sell" and last_close > current_sl)
                    
                    if sl_hit:
                        print(f"\n[LOSS] SL Hit (Close: {last_close}). Exiting.")
                        self._emergency_close(symbol, exit_side, total_qty, open_tp_ids)
                        break

                sys.stdout.write(f"\rPrice: {current_price} | SL: {current_sl} | Open TPs: {len(open_tp_ids)}   ")
                sys.stdout.flush()
                time.sleep(3)

            except KeyboardInterrupt:
                self._handle_sigint(symbol, exit_side, total_qty, open_tp_ids)
                break
            except Exception:
                time.sleep(3)

    def _monitor_single_tp(self, symbol, entry_side, exit_side, sl_price, tp_id, timeframe, total_qty):
        ccxt_tf = self._get_ccxt_timeframe(timeframe)
        print(f"   [MONITOR] Started. Hard SL: {sl_price} | Soft SL: Candle Close < {sl_price}")

        while True:
            try:
                # 1. Position Check
                if not self.adapter.check_position_active(symbol):
                    print("\n[STOP] Position closed.")
                    self.adapter.cancel_order(tp_id, symbol)
                    break

                # 2. Check TP
                if not self._is_order_open(tp_id, symbol):
                    print("\n[WIN] TP Filled.")
                    break

                # 3. Hard SL (Live Price)
                ticker = self.adapter.fetch_ticker(symbol)
                current_price = Decimal(str(ticker['last']))
                
                hard_sl_hit = (entry_side == "buy" and current_price <= sl_price) or \
                              (entry_side == "sell" and current_price >= sl_price)
                
                if hard_sl_hit:
                    print(f"\n[LOSS] HARD SL Hit ({current_price}). Exiting.")
                    self._emergency_close(symbol, exit_side, total_qty, [tp_id])
                    break

                # 4. Soft SL (Candle Close)
                ohlcv = self.adapter.fetch_ohlcv(symbol, timeframe=ccxt_tf, limit=2)
                if ohlcv:
                    last_close = Decimal(str(ohlcv[-2][4]))
                    soft_sl_hit = (entry_side == "buy" and last_close < sl_price) or \
                                  (entry_side == "sell" and last_close > sl_price)
                    
                    if soft_sl_hit:
                        print(f"\n[LOSS] SOFT SL Hit (Close: {last_close}). Exiting.")
                        self._emergency_close(symbol, exit_side, total_qty, [tp_id])
                        break

                sys.stdout.write(f"\rPrice: {current_price} | SL: {sl_price}   ")
                sys.stdout.flush()
                time.sleep(1)

            except KeyboardInterrupt:
                self._handle_sigint(symbol, exit_side, total_qty, [tp_id])
                break
            except Exception:
                time.sleep(1)

    # ==========================================================================
    # HELPERS
    # ==========================================================================

    def _emergency_close(self, symbol, side, qty, open_orders):
        for oid in open_orders:
            self.adapter.cancel_order(oid, symbol)
        self.adapter.create_order(symbol, "market", side, qty)

    def _handle_sigint(self, symbol, side, qty, open_orders):
        print("\n\nSIGINT (Manual Stop). Closing everything...")
        self._emergency_close(symbol, side, qty, open_orders)
        print("Done.")

    def _is_order_open(self, order_id, symbol):
        try:
            o = self.adapter.fetch_order(order_id, symbol)
            return o['status'] not in ['filled', 'closed', 'canceled']
        except:
            return True # Assume open on error

    @staticmethod
    def _smart_round(value: Decimal, precision: int) -> Decimal:
        if precision == 0: return value.quantize(Decimal("1"), rounding=ROUND_FLOOR)
        quantizer = Decimal("1") / Decimal(str(10**precision))
        return value.quantize(quantizer, rounding=ROUND_FLOOR)

    @staticmethod
    def _get_ccxt_timeframe(tf_str: str) -> str:
        return {'D1': '1d', 'H4': '4h', 'H1': '1h', 'M15': '15m', 'M1': '1m'}.get(tf_str, tf_str.lower())