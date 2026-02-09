from typing import List, Dict, Any
from decimal import Decimal

def create_trade(cursor, run_id: int, trade: Dict[str, Any]):
    """Insert a new trade."""
    cursor.execute("""
        INSERT INTO trades (
            run_id, symbol, side, entry_time, exit_time,
            entry_price, exit_price, quantity, size_usd,
            pnl, pnl_pct, exit_reason, hold_time_hours
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        run_id,
        trade['symbol'],
        trade['side'],
        trade['entry_time'],
        trade.get('exit_time'),
        str(trade['entry_price']),
        str(trade.get('exit_price')) if trade.get('exit_price') else None,
        str(trade['quantity']),
        str(trade['size_usd']),
        str(trade.get('pnl')) if trade.get('pnl') is not None else None,
        trade.get('pnl_pct'),
        trade.get('exit_reason'),
        trade.get('hold_time_hours')
    ))

def get_trades_by_run(cursor, run_id: int) -> List[Dict]:
    """Get all trades for a specific run."""
    cursor.execute("""
        SELECT * FROM trades
        WHERE run_id = ?
        ORDER BY entry_time ASC
    """, (run_id,))
    
    trades = []
    for row in cursor.fetchall():
        trade = dict(row)
        # Convert numeric fields back to Decimal/float where appropriate
        trade['entry_price'] = Decimal(trade['entry_price'])
        if trade['exit_price']:
            trade['exit_price'] = Decimal(trade['exit_price'])
        if trade['pnl']:
            trade['pnl'] = Decimal(trade['pnl'])
        trades.append(trade)
    return trades
