import os
import glob
from pathlib import Path
from datetime import datetime

class DataAPIMixin:
    """Methods related to data files and strategies."""

    def get_data_files(self) -> list[dict]:
        """Return list of available CSV data files."""
        # Use absolute path relative to project root
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        data_dir = os.path.join(base_dir, "app", "backtest", "data")

        files = []
        if not os.path.exists(data_dir):
            return files

        for f in glob.glob(os.path.join(data_dir, "*.csv")):
            path = Path(f)
            stat = path.stat()
            # Infer symbol/timeframe from filename: XPLUSDT_5m.csv
            parts = path.stem.split("_")

            files.append({
                "name": path.name,
                "symbol": parts[0] if len(parts) > 0 else "unknown",
                "timeframe": parts[1] if len(parts) > 1 else "unknown",
                "path": str(path.absolute()),
                "size_mb": round(stat.st_size / 1024 / 1024, 2),
                "modified": datetime.fromtimestamp(stat.st_mtime).isoformat()
            })

        return sorted(files, key=lambda x: x["modified"], reverse=True)

    def get_strategies(self) -> list[dict]:
        """Return list of available strategies."""
        # This scans the strategies directory for python files
        # Alternatively, we could maintain a registry

        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        strategies_dir = os.path.join(base_dir, "app", "strategies")

        strategies = []
        if not os.path.exists(strategies_dir):
            return strategies

        for f in glob.glob(os.path.join(strategies_dir, "*.py")):
            path = Path(f)
            if path.name == "__init__.py" or path.name == "base.py" or path.name == "loader.py":
                continue

            # Naive approach: use filename as strategy name
            name = path.stem

            # Check for override file
            override_path = os.path.join(base_dir, "config", "strategy_overrides", f"{name}.json")
            has_override = os.path.exists(override_path)

            strategies.append({
                "name": name,
                "display_name": name.replace("_", " ").title(),
                "description": f"Strategy from {path.name}",
                "has_override": has_override
            })

        return sorted(strategies, key=lambda x: x["name"])
