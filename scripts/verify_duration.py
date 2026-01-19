"""
Verify trade duration anomalies and compare exit reasons.

This script analyzes backtest reports to:
1. Calculate median trade durations for different exit types
2. Flag anomalies where positions exceed expected duration thresholds
3. Compare old (hard SL) vs new (Close by Candle) logic results

Usage:
    python scripts/verify_duration.py
"""

import os
import glob
import pandas as pd
from pathlib import Path
from datetime import timedelta


def analyze_trade_durations():
    """Analyze trade durations from backtest CSV reports."""
    
    # Find CSV directory relative to script location
    script_dir = Path(__file__).parent
    csv_dir = script_dir.parent / "app" / "backtest" / "report" / "csv"
    
    if not csv_dir.exists():
        print(f"❌ CSV directory not found: {csv_dir}")
        print("   Run a backtest first to generate reports.")
        return
    
    # Find all trade files
    trade_files = glob.glob(str(csv_dir / "backtest_trades_*.csv"))
    
    if not trade_files:
        print(f"❌ No trade files found in {csv_dir}")
        return
    
    print(f"📂 Found {len(trade_files)} trade files in {csv_dir.name}/")
    print()
    
    # Combine all trades
    all_trades = []
    for f in trade_files:
        try:
            df = pd.read_csv(f)
            all_trades.append(df)
        except Exception as e:
            print(f"  ⚠️ Failed to read {Path(f).name}: {e}")
    
    if not all_trades:
        print("❌ No trades could be loaded")
        return
    
    combined = pd.concat(all_trades, ignore_index=True)
    
    print("=" * 60)
    print("📊 TRADE DURATION ANALYSIS")
    print("=" * 60)
    print()
    
    # Overall stats
    print(f"Total trades analyzed: {len(combined)}")
    print()
    
    # Group by exit reason
    exit_reasons = combined.groupby("exit_reason").size().sort_values(ascending=False)
    print("Exit Reason Distribution:")
    for reason, count in exit_reasons.items():
        pct = count / len(combined) * 100
        print(f"  {reason:25s}: {count:5d} ({pct:5.1f}%)")
    print()
    
    # Duration analysis by exit type
    print("-" * 60)
    print("⏱️  DURATION BY EXIT TYPE")
    print("-" * 60)
    
    duration_col = "hold_duration_hours"
    if duration_col not in combined.columns:
        # Try alternative column name
        if "hold_duration_seconds" in combined.columns:
            combined[duration_col] = combined["hold_duration_seconds"] / 3600
        else:
            print("❌ No duration column found in reports")
            return
    
    for reason in exit_reasons.index:
        subset = combined[combined["exit_reason"] == reason]
        if len(subset) > 0:
            median_hours = subset[duration_col].median()
            mean_hours = subset[duration_col].mean()
            max_hours = subset[duration_col].max()
            min_hours = subset[duration_col].min()
            
            print(f"\n{reason}:")
            print(f"  Count:  {len(subset)}")
            print(f"  Median: {median_hours:.1f}h ({median_hours/24:.1f} days)")
            print(f"  Mean:   {mean_hours:.1f}h ({mean_hours/24:.1f} days)")
            print(f"  Range:  {min_hours:.1f}h - {max_hours:.1f}h")
    
    # Check for anomalies (>30 days = 720 hours for 15m timeframe)
    print()
    print("-" * 60)
    print("🚨 ANOMALY DETECTION (trades held >30 days)")
    print("-" * 60)
    
    anomaly_threshold = 720  # 30 days in hours
    anomalies = combined[combined[duration_col] > anomaly_threshold]
    
    if anomalies.empty:
        print("✅ No anomalies detected - all trades closed within 30 days")
    else:
        print(f"⚠️  Found {len(anomalies)} trades held longer than 30 days:")
        print()
        
        # Show relevant columns
        display_cols = ["symbol", "entry_time", "exit_time", duration_col, "exit_reason", "pnl_pct"]
        display_cols = [c for c in display_cols if c in anomalies.columns]
        
        pd.set_option('display.max_columns', None)
        pd.set_option('display.width', None)
        print(anomalies[display_cols].to_string(index=False))
    
    # Compare Close by Candle vs Hard SL
    print()
    print("-" * 60)
    print("📈 CLOSE BY CANDLE vs HARD SL COMPARISON")
    print("-" * 60)
    
    close_by_candle = combined[combined["exit_reason"] == "CLOSE_BY_CANDLE_SL"]
    hard_sl = combined[combined["exit_reason"] == "SL"]
    disaster_sl = combined[combined["exit_reason"] == "DISASTER_SL"]
    
    if len(close_by_candle) > 0 or len(hard_sl) > 0:
        print()
        print("                        | Close by Candle |   Hard SL  | Disaster SL")
        print("-" * 70)
        
        cbc_count = len(close_by_candle)
        sl_count = len(hard_sl)
        dsl_count = len(disaster_sl)
        
        cbc_median = close_by_candle[duration_col].median() if cbc_count > 0 else 0
        sl_median = hard_sl[duration_col].median() if sl_count > 0 else 0
        dsl_median = disaster_sl[duration_col].median() if dsl_count > 0 else 0
        
        print(f"Count:                  |    {cbc_count:6d}       |  {sl_count:6d}    |  {dsl_count:6d}")
        print(f"Median Duration (hrs):  |    {cbc_median:6.1f}       |  {sl_median:6.1f}    |  {dsl_median:6.1f}")
        
        # PnL comparison if available
        if "pnl_pct" in combined.columns:
            cbc_pnl = close_by_candle["pnl_pct"].median() if cbc_count > 0 else 0
            sl_pnl = hard_sl["pnl_pct"].median() if sl_count > 0 else 0
            dsl_pnl = disaster_sl["pnl_pct"].median() if dsl_count > 0 else 0
            print(f"Median PnL %:           |    {cbc_pnl:6.2f}       |  {sl_pnl:6.2f}    |  {dsl_pnl:6.2f}")
    else:
        print("No Close by Candle SL or Hard SL trades found in reports.")
        print("Run a backtest with the new feature enabled to compare.")
    
    print()
    print("=" * 60)
    print("✅ Analysis complete")
    print("=" * 60)


if __name__ == "__main__":
    analyze_trade_durations()
