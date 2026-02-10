# Hotfix Analysis Starter Prompt

> **Copy and paste this to start the agent on the hotfix.**

---

The analysis features (Grid Search, Walk-Forward, Sensitivity) need their backend Python code implemented. The frontend UI already calls these APIs, but the Python modules don't exist yet.

**Read these docs in order:**

1. `.agent-guide/knowledge/BACKTEST_ENGINE.md` — How the existing engine works
2. `.agent-guide/phases/HOTFIX_ANALYSIS_BACKEND.md` — Full implementation guide with code

**What to implement:**
- `app/backtest/grid_search.py` — Grid search over parameter combinations
- `app/backtest/walk_forward.py` — Rolling window train/test analysis
- `app/backtest/sensitivity.py` — Single parameter sensitivity curves
- `app/backtest/compare.py` — Compare two runs
- Wire these into the bridge API so the frontend can call them
- Update `app/backtest/__init__.py` exports

**Execution rules:**
- Auto-proceed through tasks if verification passes
- STOP and report on errors
- Use `conda run -n rsi` for all Python commands
- **Study `app/backtest/run_batch_analysis.py` → function `run_single_backtest()` (line 218)** — this is the reference pattern for running BacktestEngine programmatically

**Start with Task 1 (grid_search.py) and proceed through Task 6.**
