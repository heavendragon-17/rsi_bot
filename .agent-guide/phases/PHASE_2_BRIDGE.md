# Phase 2: PyWebView Bridge

> **Phase Type:** Backend | **Estimated Time:** 1.5 hours | **Depends On:** Phase 1

---

## 🎯 Objective

Create the PyWebView bridge that connects the React frontend to Python backend.

---

## 📖 Required Reading

Before starting, read:
- `.agent-guide/knowledge/API_REFERENCE.md`
- `docs/backend/API_CONTRACTS.md`

---

## ✅ Tasks

### Task 2.1: Create Bridge Package

Create `app/ui/__init__.py`:
```python
from .bridge import BacktestUI
from .api import BridgeAPI
```

### Task 2.2: Create Bridge Window Manager

Create `app/ui/bridge.py`:

```python
import webview
import sys
import os
from app.ui.api import BridgeAPI

class BacktestUI:
    def __init__(self, debug=False):
        self.debug = debug
        self.api = BridgeAPI()
        
    def start(self):
        """Start the UI window."""
        # Determine path to UI assets
        if getattr(sys, 'frozen', False):
            base_dir = sys._MEIPASS
        else:
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        
        ui_dir = os.path.join(base_dir, 'ui', 'dist')
        
        if not os.path.exists(ui_dir):
            # Fallback HTML if UI not built
            html_content = """
            <!DOCTYPE html>
            <html>
            <body style="font-family: sans-serif; text-align: center; padding: 50px;">
                <h1>Backtest UI - Build Required</h1>
                <p>Run <code>npm run build</code> in the <code>ui</code> directory.</p>
            </body>
            </html>
            """
            webview.create_window('Backtest UI', html=html_content, js_api=self.api, width=1280, height=800)
        else:
            webview.create_window('Backtest UI', url=os.path.join(ui_dir, 'index.html'), js_api=self.api, width=1280, height=800)
        
        webview.start(debug=self.debug)
```

### Task 2.3: Create API Package

Create `app/ui/api/__init__.py`:

```python
from .backtest import BacktestAPIMixin
from .config import ConfigAPIMixin
from .data import DataAPIMixin

class BridgeAPI(BacktestAPIMixin, ConfigAPIMixin, DataAPIMixin):
    """Combined API exposed to JavaScript via PyWebView."""
    
    def __init__(self):
        print("BridgeAPI initialized")
```

### Task 2.4: Create Data API

Create `app/ui/api/data.py`:

Implement these methods:
- `get_data_files() -> list[str]` - Return CSV files from `app/backtest/data/`
- `get_strategies() -> list[str]` - Return available strategy names

**How to get strategies:**
- Scan `app/strategies/` for files ending in `_strategy.py`
- Or maintain a registry in config

### Task 2.5: Create Config API

Create `app/ui/api/config.py`:

Implement these methods:
- `get_strategy_config(strategy_name: str) -> dict` - Get default config
- `save_strategy_config(strategy_name: str, config: dict) -> bool` - Save to JSON override
- `get_global_config() -> dict` - Read from `config.yaml`
- `save_global_config(config: dict) -> bool` - Write to `config.yaml`
- `get_themes() -> list[str]` - Get theme names from database
- `get_active_theme() -> str` - Get active theme name
- `set_active_theme(theme_name: str) -> bool` - Set active theme

**Config override pattern:**
- Strategy configs: `config/strategy_overrides/{strategy_name}.json`
- NEVER modify `.py` strategy files

### Task 2.6: Create Backtest API

Create `app/ui/api/backtest.py`:

Implement these methods:
- `run_backtest(config: dict) -> dict` - Execute backtest and return results
- `get_run_history() -> list[dict]` - Get all runs from database
- `get_run_details(run_id: int) -> dict` - Get single run details
- `get_run_timeseries(run_id: int) -> dict` - Get equity/drawdown curves
- `get_trades(run_id: int) -> list[dict]` - Get trades for run

**run_backtest flow:**
1. Parse config (strategy, symbol, dates, parameters)
2. Call existing backtest engine (`app/backtest/`)
3. Save results to database
4. Return run_id and summary metrics

### Task 2.7: Create Entry Point

Create/update `main_ui.py` at project root:

```python
import argparse
import sys
import os

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.ui.bridge import BacktestUI

def main():
    parser = argparse.ArgumentParser(description="Backtest UI Launcher")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode")
    parser.add_argument("--test", action="store_true", help="Test mode (init only)")
    args = parser.parse_args()

    if args.test:
        try:
            ui = BacktestUI(debug=args.debug)
            print("Test mode: BacktestUI initialized successfully")
        except Exception as e:
            print(f"Test mode: BacktestUI initialization failed: {e}")
            sys.exit(1)
        return

    ui = BacktestUI(debug=args.debug)
    ui.start()

if __name__ == "__main__":
    main()
```

---

## 🔍 Verification Checkpoint

### Test 1: API Initialization
```bash
python main_ui.py --test
```
**Expected:** "Test mode: BacktestUI initialized successfully"

### Test 2: API Methods
```python
from app.ui.api import BridgeAPI

api = BridgeAPI()
print(api.get_data_files())  # Should return list of CSV files
print(api.get_strategies())  # Should return strategy names
```

---

## 📤 Report Template

```
## Phase 2 Complete: PyWebView Bridge

### Created Files:
- app/ui/__init__.py
- app/ui/bridge.py (BacktestUI class)
- app/ui/api/__init__.py (BridgeAPI class)
- app/ui/api/data.py
- app/ui/api/config.py
- app/ui/api/backtest.py
- main_ui.py (entry point)

### API Methods Implemented:
- get_data_files(): ✅
- get_strategies(): ✅
- get_strategy_config(): ✅
- save_strategy_config(): ✅
- run_backtest(): ✅
- get_run_history(): ✅
- get_run_details(): ✅
- get_run_timeseries(): ✅
- get_trades(): ✅
- get_global_config(): ✅
- save_global_config(): ✅
- get_themes(): ✅
- get_active_theme(): ✅
- set_active_theme(): ✅

### Verification:
- `python main_ui.py --test`: ✅ / ❌

Awaiting "proceed" command for Phase 3.
```

---

## ⏭️ Next Phase

After user approval, proceed to `PHASE_3_BACKEND_FEATURES.md`
