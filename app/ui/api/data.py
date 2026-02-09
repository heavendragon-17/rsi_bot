from app.db.connection import get_cursor
from app.db.repositories.runs import RunsRepository
from app.db.repositories.trades import get_trades_by_run
from app.db.repositories.timeseries import load_timeseries
from app.db.repositories.themes import get_all_themes, get_theme_by_name, create_theme

class DataAPI:
    def __init__(self):
        self.runs_repo = RunsRepository()

    def get_run_history(self, filters=None):
        """Get list of past runs."""
        try:
            limit = filters.get('limit', 50) if filters else 50
            with get_cursor() as cursor:
                runs = self.runs_repo.get_recent_runs(cursor, limit=limit)
            return {"success": True, "data": runs}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_run_details(self, run_id):
        """Get full details for a single run."""
        try:
            with get_cursor() as cursor:
                run = self.runs_repo.get_run(cursor, run_id)
                if not run:
                    return {"success": False, "error": "Run not found", "error_code": "RUN_NOT_FOUND"}
                
                # Format run details
                details = {
                    "run": {
                        "id": run['id'],
                        "strategy_name": run['strategy_name'],
                        "status": run['status'],
                        "created_at": run['created_at'],
                        "git_hash": run.get('git_hash'),
                        "version": run.get('version')
                    },
                    "config": run.get('params', {}),
                    "results": {
                        "net_profit": run.get('net_profit'),
                        "net_profit_pct": run.get('net_profit_pct'),
                        "win_rate": run.get('win_rate'),
                        "profit_factor": run.get('profit_factor'),
                        "sharpe_ratio": run.get('sharpe_ratio'),
                        "max_drawdown_pct": run.get('max_drawdown_pct'),
                        "total_trades": run.get('total_trades'),
                        "exit_reasons": run.get('exit_reasons')
                    }
                }
                return {"success": True, "data": details}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_run_timeseries(self, run_id):
        """Get time-series data (lazy loaded)."""
        try:
            with get_cursor() as cursor:
                data = load_timeseries(cursor, run_id)
            return {"success": True, "data": data}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_trades(self, run_id, options=None):
        """Get trades for a run."""
        try:
            with get_cursor() as cursor:
                trades = get_trades_by_run(cursor, run_id)
                # Apply options/filtering here if needed (e.g. limit/offset)
            
            # Serialize Decimals for JSON response
            serialized_trades = []
            for t in trades:
                t_dict = dict(t)
                for k, v in t_dict.items():
                    if hasattr(v, 'isoformat'): # datetime
                         t_dict[k] = v.isoformat()
                    # Decimals are handled by PyWebView JSON encoder usually, 
                    # but safest to convert to string or float if needed. 
                    # API contract says string for prices.
                    from decimal import Decimal
                    if isinstance(v, Decimal):
                        t_dict[k] = str(v)
                serialized_trades.append(t_dict)
                
            return {"success": True, "data": serialized_trades}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_themes(self):
        """Get available themes."""
        try:
            with get_cursor() as cursor:
                themes = get_all_themes(cursor)
            return {"success": True, "data": themes}
        except Exception as e:
             return {"success": False, "error": str(e)}
             
    def get_active_theme(self):
        """Get active theme details. For now defaults to cyberpunk_neon or stored pref."""
        # In a real app, 'active_theme' might be stored in global config
        theme_name = "cyberpunk_neon" 
        try:
            with get_cursor() as cursor:
                theme = get_theme_by_name(cursor, theme_name)
            return {"success": True, "data": theme}
        except Exception as e:
             return {"success": False, "error": str(e)}

    def export_results(self, run_id, format):
        """Export results to file."""
        # Placeholder for export functionality
        return {"success": False, "error": "Not implemented yet"}
