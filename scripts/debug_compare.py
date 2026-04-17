#!/usr/bin/env python
"""
debug_compare.py — Automated CLI vs UI backtest comparison.

Usage:
    python scripts/debug_compare.py
    python scripts/debug_compare.py --symbol BTC/USDT --timeframe 15m --start 2025-06-01 --end 2025-11-01
    python scripts/debug_compare.py --no-start-server   # backend already running

Workflow:
    1. Optionally starts the backend (uvicorn) as a subprocess
    2. Downloads data if not present (using download.py --months flag)
    3. Runs the SAME backtest via CLI engine and via the REST API
       - Both use identical date-filtered data and identical config
    4. Compares key metrics side-by-side
    5. Exits 0 on full match, 1 on any diff

Re-run loop:
    Fix code → python scripts/debug_compare.py → repeat until "ALL MATCH".
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from datetime import date as date_cls
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────

PROJECT_ROOT   = Path(__file__).resolve().parent.parent
DEFAULT_SYMBOL    = "BTC/USDT"
DEFAULT_TIMEFRAME = "15m"
DEFAULT_STRATEGY  = "rsi_no_retest"
DEFAULT_START     = None   # auto-detected from CSV when omitted
DEFAULT_END       = None   # auto-detected from CSV when omitted
DEFAULT_BALANCE   = 100000.0
DEFAULT_LEVERAGE  = 10
DEFAULT_RISK_PCT  = 0.02   # 2 %

API_BASE   = "http://localhost:8000"
TOLERANCE  = 0.01   # 1 % relative tolerance for floats

# ── Helpers ───────────────────────────────────────────────────────────────────

def _csv_path(symbol: str, timeframe: str) -> Path:
    safe = symbol.replace("/", "")
    # Canonical data dir — matches workers.py / inline_download expectation
    return PROJECT_ROOT / "app" / "backtest" / "data" / f"{safe}_{timeframe}.csv"


def _ensure_data(symbol: str, timeframe: str, start: str, end: str) -> Path:
    """Download CSV if missing. Uses --months calculated from date range."""
    csv = _csv_path(symbol, timeframe)
    if csv.exists():
        print(f"  [data] {csv.name} already present — skipping download")
        return csv

    # Calculate months needed
    d_start = date_cls.fromisoformat(start)
    d_end   = date_cls.fromisoformat(end)
    months  = max(1, round((d_end - d_start).days / 30))

    # Canonical output dir (download.py default is its own subdir; override it)
    canonical_data_dir = PROJECT_ROOT / "app" / "backtest" / "data"

    print(f"  [data] Downloading {symbol} {timeframe} ({months} months) …")
    r = subprocess.run(
        [
            sys.executable,
            str(PROJECT_ROOT / "app" / "backtest" / "data" / "download.py"),
            "--symbol",    symbol,
            "--timeframe", timeframe,
            "--months",    str(months),
            "--output",    str(canonical_data_dir),
        ],
        cwd=PROJECT_ROOT,
    )
    if r.returncode != 0:
        sys.exit("ERROR: data download failed — cannot continue")
    return csv


def _start_backend() -> subprocess.Popen | None:
    """Start uvicorn and wait until /health responds."""
    import urllib.request

    print("  [backend] Starting uvicorn …")
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn",
         "app.api.main:app", "--port", "8000", "--log-level", "warning"],
        cwd=PROJECT_ROOT,
    )
    for _ in range(20):
        time.sleep(0.5)
        try:
            urllib.request.urlopen(f"{API_BASE}/health", timeout=1)
            print("  [backend] Ready ✓")
            return proc
        except Exception:
            pass
    proc.terminate()
    sys.exit("ERROR: backend did not start within 10 s — check for import errors")


def _csv_date_range(csv: Path) -> tuple[str, str]:
    """Read first and last timestamp from a CSV and return (start, end) as ISO date strings."""
    import pandas as pd
    df = pd.read_csv(csv, usecols=["timestamp"], nrows=None)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    start = df["timestamp"].min().strftime("%Y-%m-%d")
    end   = df["timestamp"].max().strftime("%Y-%m-%d")
    return start, end


def _backend_running() -> bool:
    import urllib.request
    try:
        urllib.request.urlopen(f"{API_BASE}/health", timeout=2)
        return True
    except Exception:
        return False


# ── CLI backtest (run in-process) ─────────────────────────────────────────────

def run_cli(symbol: str, timeframe: str, strategy: str,
            balance: float, start: str, end: str) -> dict:
    """Run backtest through BacktestEngine directly and return results dict."""
    import os
    import tempfile

    import pandas as pd

    sys.path.insert(0, str(PROJECT_ROOT))

    from app.backtest.config_builder import build_backtest_config
    from app.backtest.engine.backtest_engine import BacktestEngine
    from app.trading.strategy.loader import STRATEGY_MAP

    strategy_class = STRATEGY_MAP[strategy]

    # Build config the SAME way the CLI (backtest.py) does —
    # load_yaml=True (default), no extra params.
    config = build_backtest_config(
        symbol=symbol,
        timeframe=timeframe,
        strategy_name=strategy,
        initial_balance=balance,
    )
    # Remove the yaml duration so the engine doesn't truncate to 5 months —
    # we apply our own date filter below so both CLI and API use the same rows.
    config.get("backtest", {}).pop("duration", None)

    csv = _csv_path(symbol, timeframe)
    df  = pd.read_csv(csv)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    mask = (df["timestamp"] >= start) & (df["timestamp"] <= end)
    filtered = df[mask].reset_index(drop=True)
    if filtered.empty:
        sys.exit(f"ERROR: no data between {start} and {end} in {csv.name}")

    # Write temp CSV for BacktestEngine
    tmp = tempfile.NamedTemporaryFile(suffix=".csv", delete=False, mode="w")
    tmp_path = tmp.name
    tmp.close()
    filtered.to_csv(tmp_path, index=False)

    print(f"\n{'='*60}")
    print(f"  [CLI] BacktestEngine on {len(filtered)} candles ({start} → {end})")

    try:
        engine  = BacktestEngine(tmp_path, strategy_class, config)
        results = engine.run()
    finally:
        os.unlink(tmp_path)

    trades = (results.get("metrics") or {}).get("total_trades", 0)
    print(f"  [CLI] Done — {trades} trades")
    return results


# ── API backtest ──────────────────────────────────────────────────────────────

def run_api(symbol: str, timeframe: str, strategy: str,
            balance: float, start: str, end: str,
            leverage: int, risk_pct: float) -> dict:
    """POST to the API, wait for completion, return the results dict."""
    import json as _json
    import urllib.request

    payload = {
        "symbol":           symbol,
        "timeframe":        timeframe,
        "strategy":         strategy,
        "start_date":       start,
        "end_date":         end,
        "initial_capital":  str(balance),
        "leverage":         leverage,
        "risk_per_trade_pct": f"{risk_pct:.4f}",
        "params":           {},
        # Explicit risk params matching config.yaml so results equal CLI
        "tp1_close_pct":              1.0,
        "tp2_close_pct":              0.0,
        "max_position_size_pct":     10.0,
        "min_sl_distance_pct":       0.003,
        "use_risk_based_sizing":     True,
        "use_initial_capital_for_risk": True,
    }

    print(f"\n{'='*60}")
    print(f"  [API]  POST {API_BASE}/api/backtest/run")

    data = _json.dumps(payload).encode()
    req  = urllib.request.Request(
        f"{API_BASE}/api/backtest/run",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = _json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        err_body = exc.read().decode(errors="replace")
        sys.exit(
            f"ERROR: POST /api/backtest/run returned HTTP {exc.code}\n"
            f"Response body:\n{err_body}"
        )
    run_id = body["run_id"]
    print(f"  [API]  run_id={run_id} — waiting …")

    # Poll for completion (up to 3 min)
    for _ in range(180):
        time.sleep(1)
        try:
            with urllib.request.urlopen(
                f"{API_BASE}/api/backtest/{run_id}", timeout=5
            ) as r:
                detail = _json.loads(r.read())
            status = detail.get("status")
            if status == "completed":
                results = detail.get("results") or {}
                trades  = (results.get("metrics") or {}).get("total_trades", 0)
                print(f"  [API]  Done — {trades} trades")
                return results
            if status == "failed":
                sys.exit(f"ERROR: API backtest failed: {detail}")
        except Exception as e:
            print(f"  [API]  poll error: {e}")

    sys.exit("ERROR: API backtest timed out after 3 minutes")


# ── Side-by-side comparison ───────────────────────────────────────────────────

# Each extractor tries the CLI nested layout first, then the API flat layout.
def _m(nested_keys, flat_key):
    """Return getter that works for both CLI (nested) and API (flat) result dicts."""
    def getter(r):
        # Walk the nested path
        v = r
        for k in nested_keys:
            if not isinstance(v, dict):
                v = None
                break
            v = v.get(k)
        if v is not None:
            return v
        # Fall back to flat key (API)
        return r.get(flat_key)
    return getter

METRICS = [
    ("Total trades",  _m(["metrics", "total_trades"],          "total_trades")),
    ("Win rate %",    _m(["metrics", "win_rate"],               "win_rate")),
    ("Net profit",    _m(["net_profit"],                        "net_profit")),
    ("Net profit %",  _m(["net_profit_pct"],                    "net_profit_pct")),
    ("Profit factor", _m(["metrics", "profit_factor"],          "profit_factor")),
    ("Max DD %",      _m(["drawdown", "max_drawdown_pct"],      "max_drawdown_pct")),
    ("Sharpe ratio",  _m(["risk_metrics", "sharpe_ratio"],      "sharpe_ratio")),
    ("Gross profit",  _m(["metrics", "gross_profit"],           "gross_profit")),
    ("Gross loss",    _m(["metrics", "gross_loss"],             "gross_loss")),
    ("Final balance", _m(["final_balance"],                     "final_balance")),
]

def _rel_diff(a, b) -> float | None:
    if a is None or b is None:
        return None
    try:
        a, b = float(a), float(b)
        denom = max(abs(a), abs(b), 1e-9)
        return abs(a - b) / denom
    except (TypeError, ValueError):
        return None


def compare(cli: dict, api: dict) -> bool:
    COL = 20
    print(f"\n{'='*72}")
    print(f"  {'Metric':<{COL}} {'CLI':>16}  {'API':>16}  {'Diff':>8}  Status")
    print(f"  {'-'*COL} {'-'*16}  {'-'*16}  {'-'*8}  ------")

    all_ok = True
    for label, getter in METRICS:
        cv   = getter(cli)
        av   = getter(api)
        diff = _rel_diff(cv, av)

        if diff is None:
            status = "MISSING"
            all_ok = False
        elif diff <= TOLERANCE:
            status = "OK ✓"
        else:
            status = f"MISMATCH ✗ ({diff*100:.1f}%)"
            all_ok = False

        cv_s = f"{float(cv):.4f}" if isinstance(cv, (int, float)) else str(cv)
        av_s = f"{float(av):.4f}" if isinstance(av, (int, float)) else str(av)
        diff_s = "—" if diff is None else f"{diff*100:.2f}%"
        print(f"  {label:<{COL}} {cv_s:>16}  {av_s:>16}  {diff_s:>8}  {status}")

    print(f"{'='*72}")
    if all_ok:
        print("  ✅  ALL MATCH — CLI and UI produce identical results.")
    else:
        print("  ❌  DIFFERENCES FOUND — see rows marked MISMATCH above.")
    print(f"{'='*72}\n")
    return all_ok


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description="Compare CLI vs UI backtest results")
    ap.add_argument("--symbol",          default=DEFAULT_SYMBOL)
    ap.add_argument("--timeframe",       default=DEFAULT_TIMEFRAME)
    ap.add_argument("--strategy",        default=DEFAULT_STRATEGY)
    ap.add_argument("--start",           default=DEFAULT_START)
    ap.add_argument("--end",             default=DEFAULT_END)
    ap.add_argument("--balance",  type=float, default=DEFAULT_BALANCE)
    ap.add_argument("--leverage", type=int,   default=DEFAULT_LEVERAGE)
    ap.add_argument("--risk-pct", type=float, default=DEFAULT_RISK_PCT)
    ap.add_argument("--no-start-server", action="store_true",
                    help="Skip starting the backend (use if already running)")
    args = ap.parse_args()

    print("\n" + "="*72)
    print("  backtest debug_compare.py")
    print(f"  Symbol: {args.symbol}   Timeframe: {args.timeframe}   Strategy: {args.strategy}")
    print(f"  Period: {args.start}  →  {args.end}")
    print(f"  Balance: ${args.balance:,.0f}  Leverage: {args.leverage}x  Risk: {args.risk_pct*100:.1f}%")
    print("="*72)

    # 1. Data
    print("\n[1/4] Checking data …")
    # Resolve start/end: download first with a 5-month window when dates unknown,
    # then read the actual range from the CSV so both runs use real data.
    placeholder_start = args.start or "2025-01-01"
    placeholder_end   = args.end   or date_cls.today().isoformat()
    csv = _ensure_data(args.symbol, args.timeframe, placeholder_start, placeholder_end)

    if args.start is None or args.end is None:
        detected_start, detected_end = _csv_date_range(csv)
        args.start = args.start or detected_start
        args.end   = args.end   or detected_end
        print(f"  [data] Using full CSV range: {args.start} → {args.end}")

    # Update printed header now that we know the real dates
    print(f"  Symbol: {args.symbol}  Timeframe: {args.timeframe}  "
          f"Period: {args.start} → {args.end}")

    # 2. Backend
    backend_proc = None
    print("\n[2/4] Backend …")
    if args.no_start_server:
        if not _backend_running():
            sys.exit("ERROR: --no-start-server but backend not reachable at " + API_BASE)
        print("  Already running ✓")
    else:
        if _backend_running():
            print("  Already running ✓")
        else:
            backend_proc = _start_backend()

    try:
        # 3. Run both
        print("\n[3/4] Running backtests …")
        cli_results = run_cli(
            args.symbol, args.timeframe, args.strategy,
            args.balance, args.start, args.end,
        )
        api_results = run_api(
            args.symbol, args.timeframe, args.strategy,
            args.balance, args.start, args.end,
            args.leverage, args.risk_pct,
        )

        # 4. Compare
        print("\n[4/4] Comparing results …")
        ok = compare(cli_results, api_results)

    finally:
        if backend_proc is not None:
            print("  [backend] Stopping …")
            backend_proc.terminate()
            backend_proc.wait()

    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
