import json
from typing import List, Dict, Any, Optional
from decimal import Decimal
from datetime import datetime

class RunsRepository:
    def create_run(self, cursor, strategy_id: int, status: str = "pending", config: Dict = None) -> int:
        """Create a new run and return its ID."""
        # Insert run
        cursor.execute("""
            INSERT INTO runs (strategy_id, status, created_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
        """, (strategy_id, status))
        run_id = cursor.lastrowid
        
        # Insert config if provided
        if config:
            self.save_run_config(cursor, run_id, config)
            
        return run_id

    def update_status(self, cursor, run_id: int, status: str, started_at: datetime = None, completed_at: datetime = None):
        """Update run status and timestamps."""
        params = [status]
        query = "UPDATE runs SET status = ?"
        
        if started_at:
            query += ", started_at = ?"
            params.append(started_at)
        if completed_at:
            query += ", completed_at = ?"
            params.append(completed_at)
            
        query += " WHERE id = ?"
        params.append(run_id)
        
        cursor.execute(query, params)

    def save_run_config(self, cursor, run_id: int, config: Dict):
        """Save run configuration."""
        cursor.execute("""
            INSERT INTO run_configs (
                run_id, symbol, timeframe, start_date, end_date,
                initial_capital, risk_per_trade_pct, params
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            run_id,
            config.get('symbol'),
            config.get('timeframe'),
            config.get('start_date'),
            config.get('end_date'),
            str(config.get('initial_capital', '10000.00')),
            str(config.get('risk_per_trade_pct', '0.02')),
            json.dumps(config.get('params', {}))
        ))

    def save_results(self, cursor, run_id: int, results: Dict):
        """Save run results."""
        cursor.execute("""
            INSERT INTO run_results (
                run_id, net_profit, net_profit_pct, win_rate, 
                max_drawdown_pct, sharpe_ratio, total_trades, exit_reasons
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            run_id,
            str(results.get('net_profit', 0)),
            results.get('net_profit_pct'),
            results.get('win_rate'),
            results.get('max_drawdown_pct'),
            results.get('sharpe_ratio'),
            results.get('total_trades'),
            json.dumps(results.get('exit_reasons', {}))
        ))

    def get_run(self, cursor, run_id: int) -> Optional[Dict]:
        """Get run details by ID."""
        cursor.execute("""
            SELECT r.*, s.name as strategy_name, rc.symbol, rc.timeframe, rc.params
            FROM runs r
            JOIN strategies s ON r.strategy_id = s.id
            LEFT JOIN run_configs rc ON r.id = rc.run_id
            WHERE r.id = ?
        """, (run_id,))
        row = cursor.fetchone()
        if not row:
            return None
        
        result = dict(row)
        if result.get('params'):
            result['params'] = json.loads(result['params'])
        return result

    def get_recent_runs(self, cursor, limit: int = 50) -> List[Dict]:
        """Get recent runs for dashboard."""
        cursor.execute("""
            SELECT r.id, s.name as strategy_name, 
                   rr.net_profit_pct, rr.sharpe_ratio, rr.win_rate,
                   rc.symbol, rc.timeframe,
                   r.created_at, r.status
            FROM runs r
            JOIN strategies s ON r.strategy_id = s.id
            LEFT JOIN run_results rr ON r.id = rr.run_id
            LEFT JOIN run_configs rc ON r.id = rc.run_id
            ORDER BY r.created_at DESC
            LIMIT ?
        """, (limit,))
        return [dict(row) for row in cursor.fetchall()]
