import zlib
import json
from typing import List, Dict, Any, Optional

def compress_timeseries(data: List[Dict]) -> bytes:
    """Compress JSON list to BLOB for storage."""
    json_str = json.dumps(data)
    return zlib.compress(json_str.encode('utf-8'))

def decompress_timeseries(blob: Optional[bytes]) -> List[Dict]:
    """Decompress BLOB to JSON list."""
    if not blob:
        return []
    try:
        json_str = zlib.decompress(blob).decode('utf-8')
        return json.loads(json_str)
    except Exception as e:
        print(f"Error decompressing timeseries: {e}")
        return []

def save_timeseries(cursor, run_id: int, equity: List[Dict], drawdown: List[Dict] = None, monthly: Dict = None):
    """Save compressed time-series to run_timeseries table."""
    cursor.execute("""
        INSERT OR REPLACE INTO run_timeseries (run_id, equity_curve, drawdown_curve, monthly_returns)
        VALUES (?, ?, ?, ?)
    """, (
        run_id,
        compress_timeseries(equity),
        compress_timeseries(drawdown) if drawdown else None,
        json.dumps(monthly) if monthly else None
    ))

def load_timeseries(cursor, run_id: int) -> Dict[str, Any]:
    """Load and decompress time-series from database."""
    cursor.execute("""
        SELECT equity_curve, drawdown_curve, monthly_returns
        FROM run_timeseries WHERE run_id = ?
    """, (run_id,))
    row = cursor.fetchone()
    
    if not row:
        return {'equity_curve': [], 'drawdown_curve': [], 'monthly_returns': {}}
    
    return {
        'equity_curve': decompress_timeseries(row['equity_curve']),
        'drawdown_curve': decompress_timeseries(row['drawdown_curve']),
        'monthly_returns': json.loads(row['monthly_returns']) if row['monthly_returns'] else {}
    }
