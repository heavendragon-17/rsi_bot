# Common Issues

> Top issues with symptoms, causes, and solutions.

---

| # | Issue | Symptom | Cause | Solution |
|---|-------|---------|-------|----------|
| 1 | ModuleNotFoundError | `No module named 'ccxt'` | Missing dependency | `pip install -r requirements.txt` in conda env |
| 2 | API key not found | `KeyError: 'BINANCE_API_KEY'` | Missing `.env` | Copy `.env.example` to `.env`, fill in keys |
| 3 | Testnet connection refused | Connection timeout to testnet | Binance testnet down | Check testnet status, try again later |
| 4 | Position size zero | No trade entered despite signal | SL too close (`< min_sl_distance_pct`) | Increase `min_sl_distance_pct` or check SL calculation |
| 5 | Leverage not set | `OrderRejectedError` on entry | Exchange mode mismatch | Verify `bot.mode` matches credentials in `.env` |
| 6 | WebSocket drops repeatedly | Frequent `stream_disconnected` | Network or Binance issue | Check connectivity, check Binance status page |
| 7 | Backtest hangs | No progress output | Data loading issue | Check CSV exists, correct format, path is valid |
| 8 | SSE connection drops | Frontend stops receiving events | CORS or timeout | Check CORS allows `localhost:3100` or the configured origin; check FastAPI keepalive |
| 9 | Strategy not found | `KeyError` in strategy loader | Not registered | Check `loader.py` STRATEGY_MAP + run `seed_strategies()` |
| 10 | Indicators NaN | RSI/EMA values are NaN | Insufficient warmup candles | Increase `warmup_candles` (default 220) |
| 11 | "Reduce only" rejected | `OrderRejectedError` on exit | Position already closed | Hard SL fired before soft SL; `_handle_soft_sl_exit()` handles this |
| 12 | Database locked | `OperationalError: database is locked` | Concurrent SQLite access | Ensure only 1 uvicorn worker (`--workers 1`) |
| 13 | Conda env not found | `EnvironmentNotFoundError` | Wrong activation command | `source C:/ProgramData/miniconda3/Scripts/activate rsi` |
| 14 | CSV not found | Backtest fails: "file not found" | Data not downloaded | Run `python app/backtest/data/download.py` first |
| 15 | Decimal conversion error | `InvalidOperation` | Float string passed to Decimal | Check data source — CSV may have malformed numbers |
